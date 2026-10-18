use spectrum_agent::engine_path::EngineSelection;
use std::path::PathBuf;

#[test]
fn constructor_precedes_resource_and_rejects_non_engine_or_relative_paths() {
    let selected = EngineSelection::resolve(
        Some(PathBuf::from(r"E:\fixture\app.exe")),
        || unreachable!(),
    );
    assert_eq!(selected.source, "constructor_injection");
    assert!(selected.valid_shape());
    for path in ["app.exe", r"E:\Python\python.exe", ""] {
        assert!(!EngineSelection::development(path.into()).valid_shape());
    }
}
