"""Bind an explicit processing answer to versions already shown by real tools.

No latest-version database lookup, execution, or content-derived authorization.
The stored selection is server-owned evidence; tool arguments must still carry
all three references and match that evidence.
"""
from hashlib import sha256
import json
import re

from backend.database import connect_database
from .authorization import NEGATION, QUESTION, QUERY, dataset_references, unquoted


def requested(content):
    text=unquoted(content)
    return bool(re.search(r'预处理|(?:使用|采用|用)(?:默认|上述|这个|该)(?:配方|方案)',text)
                and not re.search(NEGATION+'|'+QUESTION+'|'+QUERY,text))


def capture(database,sid,content,state,request_id):
    previous=state.pop('preprocess_selection',None)
    if not requested(content):
        return
    text=unquoted(content)
    if re.search(r'除了?|排除|不包括|不包含|不含|最新|本轮|本次|这次|刚才|标注(?:版本)?\s*[vV]\d+',text):
        return  # Changed/excluded versions use the existing explicit-reference path.
    with connect_database(database) as db:
        registered=[row[0] for row in db.execute('SELECT id FROM dataset_registry ORDER BY rowid')]
        if not registered:
            return  # No saved selection can exist; leave discovery to the workflow.
        if re.search(r'(?:全部|所有)(?:已导入的?|的)?(?:数据(?:集)?|样品)',text):
            cubes=registered
        else:
            cubes=dataset_references(text,state.get('dataset_catalog',[]))
            cubes.extend(cube for cube in registered if cube in text)
            cubes.extend(row['id'] for row in state.get('dataset_catalog',[]) if row.get('name')
                         and re.search(r'(?<![A-Za-z0-9_])'+re.escape(row['name'])+r'(?![A-Za-z0-9_])',text))
        cubes=list(dict.fromkeys(cubes))
        if not cubes or len(cubes)>32 or any(cube not in registered for cube in cubes):
            return
        rows=db.execute("SELECT s.tool,s.result_summary,shown.assistant_content,r.id FROM agent_step s "
                        "JOIN agent_round r ON r.id=s.round_id JOIN agent_round shown ON shown.id=("
                        "SELECT d.id FROM agent_round d WHERE d.session_id=r.session_id "
                        "AND COALESCE(d.turn_id,d.id)=COALESCE(r.turn_id,r.id) "
                        "AND d.status='done' AND d.assistant_content IS NOT NULL ORDER BY d.rowid DESC LIMIT 1) "
                        "WHERE s.session_id=? AND s.status='ok' AND r.status='done' "
                        "AND s.tool IN ('annotations.context','annotations.status_batch','preprocess.recipes') ORDER BY s.rowid DESC LIMIT 256",(sid,)).fetchall()
        annotations,recipes={},None
        seen=set()
        sources={}
        for tool,raw,answer,round_id in rows:
            value=json.loads(raw)
            contexts=([value] if tool=='annotations.context' else [
                {key.removeprefix(f'item_{i}_'):entry for key,entry in value.items() if key.startswith(f'item_{i}_')}
                for i in range(1,min(value.get('member_count',0),32)+1)] if tool=='annotations.status_batch' else [])
            for context in contexts:
                cube=context.get('cube_id')
                if not cube or cube in seen:continue
                seen.add(cube)
                # A completed, displayed saved-version observation is confirmable;
                # an unseen candidate or a result from this new request is not.
                if context.get('saved_version_available') is True and context.get('latest_annotation_version_id') and re.search(r'标注|版本|保存',answer):
                    annotations[cube]=context['latest_annotation_version_id']
                    sources[cube]=round_id
            if tool=='preprocess.recipes' and recipes is None:
                recipes=[{'id':value[f'recipe_{i}_version_id'],'name':value.get(f'recipe_{i}_name',''),
                          'default':value.get(f'recipe_{i}_is_default') is True,'ref':'P'+str(i)}
                         for i in range(1,min(value.get('recipe_count',0),50)+1)
                         if value.get(f'recipe_{i}_version_id')]
        if recipes is None or any(cube not in annotations for cube in cubes):
            return
        chosen=[]
        if re.search(r'默认(?:配方|方案)|默认.*预处理',text):
            chosen=[item['id'] for item in recipes if item['default']]
        else:
            chosen=[item['id'] for item in recipes if item['id'] in text or item['name'] and item['name'] in text
                    or re.search(r'(?<![A-Za-z0-9_-])'+item['ref']+r'(?![A-Za-z0-9_-])',text,re.I)]
        explicit_recipe=bool(re.search(r'默认|(?<![A-Za-z0-9_-])P\d+(?![A-Za-z0-9_-])|配方版本|recipe_version_id',text,re.I)
                             or re.search(r'配方|方案',re.sub(r'(?:上述|这个|该)(?:配方|方案)','',text))
                             or any(item['id'] in text or item['name'] and item['name'] in text for item in recipes))
        if not chosen and previous and not explicit_recipe:
            # Preserve a recipe the user actually selected, never select a new
            # default merely because the next request changes the member scope.
            chosen=[previous['recipe_version_id']] if any(item['id']==previous.get('recipe_version_id') for item in recipes) else []
        if not chosen and not explicit_recipe:
            last=db.execute("SELECT assistant_content FROM agent_round WHERE session_id=? AND status='done' "
                            "AND assistant_content IS NOT NULL ORDER BY rowid DESC LIMIT 1",(sid,)).fetchone()
            offer=last[0] if last else ''
            if re.search(r'预处理',offer) and re.search(r'是否|确认|[?？]',offer):
                chosen=[item['id'] for item in recipes if item['name'] and item['name'] in offer]
        if len(chosen)!=1:
            return
        literals=re.findall(r'(?<![A-Za-z0-9_-])[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?![A-Za-z0-9_-])',text,re.I)
        if any(value not in {*cubes,chosen[0],*(annotations[cube] for cube in cubes)} for value in literals):
            return  # A different literal version must use the explicit-reference path.
    state['preprocess_selection']={
        'source_request_id':request_id,'source_digest':sha256(content.encode()).hexdigest(),
        'recipe_version_id':chosen[0],'observation_rounds':sources,
        'inputs':[dict(cube_id=cube,annotation_version_id=annotations[cube],recipe_version_id=chosen[0]) for cube in cubes]}


def selected_inputs(state,content):
    selection=state.get('preprocess_selection')
    if not selection or selection.get('source_digest')!=sha256(content.encode()).hexdigest():
        return None
    return selection['inputs']
