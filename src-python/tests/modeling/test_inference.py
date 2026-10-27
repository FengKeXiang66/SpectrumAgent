"""End-to-end persisted inference, numerical equivalence and rejection boundaries."""
from copy import deepcopy
import base64
import json
import struct
from uuid import uuid4
import zlib

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.cross_decomposition import PLSRegression
import sklearn

from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.modeling import ModelingError
from spectrumagent.modeling.registry import ModelRegistry, encode
from spectrumagent.modeling.inference import InferenceRuns, apply_with_calibration, predict, WARNING
from spectrumagent.modeling.run import TrainingRuns
from spectrumagent.display.falsecolor import concentration_colors, CONCENTRATION_PALETTE


def trained(factory, pipeline=None):
    c = factory()
    c.targets.import_csv(c.project,c.csv_text)
    if pipeline:
        with connect_database(c.paths.database) as db:
            db.execute("UPDATE preprocess_recipe_version SET pipeline=?", (json.dumps(pipeline),))
    c.training = TrainingRuns(c.registry,c.paths)
    c.result = c.training.regress(**c.arguments)
    c.models = ModelRegistry(c.registry,c.paths)
    c.model = c.models.register(c.result["run_id"])
    c.engine = InferenceRuns(c.registry,c.paths)
    return c


def image_case(c, tmp_path, *, bands=8, axis=None, nonfinite=False):
    rng = np.random.default_rng(143)
    x = rng.uniform(-2,3,(65,4,bands)).astype(np.float64)
    if nonfinite:
        x[33,1,0] = np.nan
    header = tmp_path / (str(uuid4())+".hdr")
    header.with_suffix(".img").write_bytes(x.tobytes())
    header.write_text(f"ENVI\nlines=65\nsamples=4\nbands={bands}\ndata type=5\ninterleave=bip\nbyte order=0\n"
                      + ("" if axis is None else "wavelength={"+",".join(map(str,axis))+"}\n"),"utf-8")
    cube = str(c.registry.import_path(str(header),raw=True).datasets[0].id)
    version,run = str(uuid4()),str(uuid4())
    folder = c.paths.snapshots/cube/"v1";folder.mkdir(parents=True)
    labels = np.tile(np.array([-2,-1,0,1],np.int32),(65,1))
    np.savez_compressed(folder/"label_map.npz",label_map=labels)
    (folder/"label_index.json").write_text(json.dumps({"0":c.label_ids["BG"],"1":c.label_ids["PE"]}),"utf-8")
    with connect_database(c.paths.database) as db:
        recipe = db.execute("SELECT recipe_version_id FROM preprocess_run WHERE id=?",(c.runs[0],)).fetchone()[0]
        db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) VALUES (?,?,1,?,260,130,'{}','fixture')",(version,cube,f"{cube}/v1"))
        db.execute("INSERT INTO preprocess_run (id,cube_id,annotation_version_id,recipe_version_id,b01_branch,input_fingerprint,status,created_at) VALUES (?,?,?,?,'passthrough',?,'succeeded','fixture')",(run,cube,version,recipe,str(uuid4())))
    return {"model_id":c.model["id"],"cube_id":cube,"preprocess_run_id":run,"annotation_version_id":version},x,labels


def artifact(c,run,kind):
    with connect_database(c.paths.database) as db:
        ref = db.execute("SELECT relative_path FROM inference_artifact WHERE run_id=? AND kind=?",(run,kind)).fetchone()[0]
    return c.paths.root/ref


def test_manual_pls_matches_sklearn_and_is_flat():
    rng=np.random.default_rng(134); x=rng.normal(size=(68,31)); y=rng.normal(size=68)
    fitted=PLSRegression(n_components=4).fit(x,y)
    model={"coef":fitted.coef_.tolist(),"intercept":fitted.intercept_.tolist(),"x_mean":fitted._x_mean.tolist()}
    actual=predict(x,model)
    assert actual.shape == (68,)
    np.testing.assert_allclose(actual,fitted.predict(x).ravel(),rtol=1e-13,atol=1e-13)
    assert np.array_equal(actual,np.concatenate([predict(x[i:i+8],model) for i in range(0,68,8)]))
    print(f"C6 sklearn={sklearn.__version__}; shape={actual.shape}; max_diff={np.max(np.abs(actual-fitted.predict(x).ravel()))}")


@pytest.mark.parametrize("pipeline",[
    {"steps":[{"op":"standardize","version":1,"params":{"method":"standard"}}]},
    {"steps":[{"op":"standardize","version":1,"params":{"method":"minmax"}}]},
    *[{"steps":[{"op":op,"version":1,"params":{"n_components":3}}]} for op in ("pca","mnf","ica")],
])
def test_persisted_images_exact_across_blocks_and_foreground_only(regression_factory,tmp_path,pipeline):
    c=trained(regression_factory,pipeline)
    request,x,labels=image_case(c,tmp_path)
    with connect_database(c.paths.database) as db:
        # Force a measured quality boundary, independently of the synthetic fit.
        db.execute("UPDATE metric SET value=2 WHERE run_id=? AND name='rpd'",(c.result["run_id"],))
        old_artifacts=db.execute("SELECT * FROM model_artifact ORDER BY id").fetchall()
    a=c.engine.create(**request,block_rows=8); b=c.engine.create(**request,block_rows=32)
    assert a["status"] == b["status"] == "succeeded"
    pred=np.load(artifact(c,a["id"],"prediction"))
    assert np.array_equal(pred,np.load(artifact(c,b["id"],"prediction")))
    assert a["stats"] == b["stats"]
    cal=c.models.get(c.model["id"],calibration=True)["calibration"]
    transformed=apply_with_calibration(cal,cal["pipeline"],x.reshape(-1,x.shape[2]))
    assert np.array_equal(pred.ravel(),predict(transformed,cal["model"]))
    fg=pred[labels == 1]; stats=a["stats"]
    assert stats["n_foreground"] == 65 and stats["n_pixels"] == 260
    assert stats["mean"] == stats["pixel_mean"] == fg.mean()
    assert stats["mean"] != pred.mean()
    assert stats["std"] == fg.std()
    assert stats["warning"] == WARNING and stats["quality_label"] == "仅可做半定量"
    np.testing.assert_allclose(stats["sample_prediction"],predict(apply_with_calibration(cal,cal["pipeline"],x[labels==1].mean(axis=0)[None,:]),cal["model"])[0])
    expected_ood=np.mean((transformed<cal["feature_min"]) | (transformed>cal["feature_max"]),axis=1).reshape(65,4)
    assert np.array_equal(expected_ood,np.load(artifact(c,a["id"],"applicability")))
    assert stats["out_of_domain_count"] == np.count_nonzero(expected_ood[labels==1] > 0)
    assert stats["below_range_count"] == np.count_nonzero(fg<stats["low"])
    assert stats["above_range_count"] == np.count_nonzero(fg>stats["high"])
    assert stats["out_of_range_count"] == stats["below_range_count"]+stats["above_range_count"] > 0
    mapped=c.engine.map(a["id"])
    assert mapped["low"] == c.model["applicability"]["y_min"] and mapped["high"] == c.model["applicability"]["y_max"]
    png=base64.b64decode(mapped["png_base64"]); assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">IIBBBBB",png[16:29]) == (4,65,8,2,0,0,0)
    assert np.array_equal(np.load(artifact(c,a["id"],"state"))[0], [0,0,1,2])
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM inference_artifact").fetchone()[0] == 8
        assert db.execute("SELECT * FROM model_artifact ORDER BY id").fetchall() == old_artifacts
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    print(f"C8-C15 {pipeline['steps'][0]}: 65x4 raster exact8/32, foreground65, clipping={stats['out_of_range_count']}")


@pytest.mark.parametrize("kind,code",[
    ("recipe","RECIPE_MISMATCH"),("axis","WAVELENGTH_AXIS_MISMATCH"),("features","FEATURE_COUNT_MISMATCH"),
    ("version","VERSION_CUBE_MISMATCH"),("binding","PREPROCESS_RUN_NOT_READY"),
    ("calibration","CALIBRATION_MISMATCH"),("processed_features","FEATURE_COUNT_MISMATCH"),
])
def test_preflight_errors_zero_rows_and_directories(regression_factory,tmp_path,kind,code):
    c=trained(regression_factory)
    args,_,_=image_case(c,tmp_path,bands=7 if kind=="features" else 8,axis=list(range(8)) if kind=="axis" else None)
    with connect_database(c.paths.database) as db:
        if kind=="recipe":
            recipe=c.runner.recipes.create("different","different",None,{"steps":[]})["versions"][0]["id"]
            db.execute("UPDATE preprocess_run SET recipe_version_id=? WHERE id=?",(recipe,args["preprocess_run_id"]))
        elif kind=="version":
            args["annotation_version_id"]=c.versions[0]
        elif kind=="binding":
            db.execute("UPDATE preprocess_run SET annotation_version_id=? WHERE id=?",(c.versions[0],args["preprocess_run_id"]))
        elif kind=="calibration":
            cal=c.models.get(c.model["id"],calibration=True)["calibration"];cal["steps"][0]["version"]=99
            db.execute("UPDATE model_registry SET calibration=?",(encode(cal),))
        elif kind=="processed_features":
            app=deepcopy(c.model["applicability"]);app["n_features"]=9
            db.execute("UPDATE model_registry SET applicability=?",(encode(app),))
    with pytest.raises(ModelingError) as caught:
        c.engine.create(**args)
    assert caught.value.code == code
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM inference_run").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM inference_artifact").fetchone()[0] == 0
    assert not (c.paths.root/"inferences").exists()
    print(f"ZERO_WRITES {kind}: {code}; inference_run=0; directories=0")


def test_nonfinite_rejected_block_failed_run_no_fake_zero_or_artifacts(regression_factory,tmp_path):
    c=trained(regression_factory);args,_,_=image_case(c,tmp_path,nonfinite=True)
    with pytest.raises(ModelingError) as caught:
        c.engine.create(**args)
    assert caught.value.code == "NON_FINITE_SPECTRA"
    with connect_database(c.paths.database) as db:
        identifier,status,stats=db.execute("SELECT id,status,stats FROM inference_run").fetchone()
        assert status == "failed" and stats is None
        assert db.execute("SELECT count(*) FROM inference_artifact").fetchone()[0] == 0
    assert not (c.paths.root/"inferences"/identifier).exists()


def test_fixed_palette_extremes_and_constant_domain():
    rgb=concentration_colors(np.array([-10.,0,1,10]),0,1)
    assert rgb.tolist() == [CONCENTRATION_PALETTE[0],CONCENTRATION_PALETTE[0],CONCENTRATION_PALETTE[-1],CONCENTRATION_PALETTE[-1]]
    assert np.array_equal(concentration_colors(np.array([.5]),0,1)[0],CONCENTRATION_PALETTE[2])
    assert np.isfinite(concentration_colors(np.ones((2,3)),1,1)).all()
    with pytest.raises(ValueError):
        concentration_colors(np.array([np.nan]),0,1)


def test_six_rest_operations_strict_requests_map_integrity_and_no_paths(regression_factory,tmp_path):
    c=trained(regression_factory);args,_,_=image_case(c,tmp_path)
    identity=EngineIdentity()
    with TestClient(create_app(c.paths,identity)) as client:
        client.headers["Authorization"]="Bearer "+identity.token
        root="/api/v1/models"
        registered=client.post(root+"/registry",json={"run_id":c.result["run_id"],"name":"rest"})
        assert registered.status_code == 200, registered.text
        model=registered.json()
        assert any(row["id"]==model["id"] for row in client.get(root+"/registry").json())
        assert client.put(root+"/registry/"+model["id"]+"/stage",json={"stage":"production"}).json()["stage"] == "production"
        args["model_id"]=model["id"]
        response=client.post(root+"/inference-runs",json=args)
        assert response.status_code == 200,response.text
        run=response.json()
        assert client.get(root+"/inference-runs/"+run["id"]).json()==run
        mapped=client.get(root+"/inference-runs/"+run["id"]+"/map")
        assert mapped.status_code == 200
        assert WARNING in mapped.json()["stats"]["warning"]
        assert "relative_path" not in mapped.text and str(c.paths.root) not in mapped.text
        assert client.post(root+"/inference-runs",json={**args,"pipeline":{"steps":[]}}).status_code == 400
        assert client.post(root+"/registry",json={"run_id":c.result["run_id"],"url":"http://bad"}).status_code == 400
        assert client.put(root+"/registry/"+model["id"]+"/stage",json={"stage":"other"}).status_code == 400
        artifact(c,run["id"],"map").write_text("{}","utf-8")
        assert client.get(root+"/inference-runs/"+run["id"]+"/map").json()["error"] == "INVALID_ARTIFACT"
        assert client.get(root+"/inference-runs/"+run["id"]).json()["stats"] == run["stats"]
