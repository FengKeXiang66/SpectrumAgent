import { settings } from '../settings/settings-forward';
import { annotations } from '../annotation/api';
import { datasets } from '../datasets/api';
import { invoke } from '@tauri-apps/api/core';
import type { Scalars } from './sse';

export const localCommandPattern=/^(?:打开(?:设置|模型设置)|(?:开启|关闭)(?:LLM)?外发|检查模型连接|运行冒烟测试|选择(?:数据源|输出)目录|设置(?:数据源|输出目录|模型|接口地址|API\s*KEY)为[\s\S]+)[。！!\s]*$/i;
type Dependencies={settings:typeof settings;projects:typeof annotations.projects;choose:typeof datasets.chooseDirectories;smoke:()=>Promise<unknown>};
const defaults:Dependencies={settings,projects:()=>annotations.projects(),choose:()=>datasets.chooseDirectories(),smoke:()=>invoke('run_smoke')};

export function localInputLabel(text:string):string {
  return /^设置API\s*KEY为/i.test(text.trim())?'设置 API KEY（内容已隐藏）':text;
}

export async function executeLocalCommand(text:string,dependencies:Dependencies=defaults):Promise<{content:string;summary?:Scalars}> {
  // Values such as API keys and paths may legitimately end in punctuation.
  const raw=text.trim();
  const value=raw.startsWith('设置')?raw:raw.replace(/[。！!]+$/,'').trim();
  if(/^打开(?:设置|模型设置)$/.test(value))return {content:'已打开本地设置。',summary:{view_kind:'settings'}};
  if(value==='运行冒烟测试')return {content:'引擎自检完成：'+JSON.stringify(await dependencies.smoke())};
  if(value==='检查模型连接') {
    const result=await dependencies.settings.verifyLLM();
    return {content:`模型连接：${result.status}。${result.detail}`};
  }
  if(/^(?:选择(?:数据源|输出)目录|设置(?:数据源|输出目录)为)/.test(value)) {
    const projects=await dependencies.projects();
    if(projects.length!==1)throw new Error('请先明确需要配置的项目。');
    const project=projects[0].id;
    const before=await dependencies.settings.getProjectPaths(project);
    const chosen=value.startsWith('选择')?(await dependencies.choose())?.[0]:value.slice(value.indexOf('为')+1);
    if(!chosen)return {content:'目录选择已取消，配置保持原值。'};
    const source=/数据源/.test(value);
    const after=await dependencies.settings.putProjectPaths(project,{source_path:source?chosen:before.source_path,output_root:source?before.output_root:chosen});
    return {content:source?'数据源目录已登记，可以继续导入。':after.output_enabled?'输出目录已登记并可用。':'输出目录已登记；启用时机遵循引擎写守卫，不会自动重启应用。'};
  }
  const key=/^设置API\s*KEY为([\s\S]+)$/i.exec(value);
  if(key){await dependencies.settings.putKey(key[1].trim());return {content:'API KEY 已在本机保存。'};}
  const config=await dependencies.settings.getLLM();
  if(/^(开启|关闭)(?:LLM)?外发$/i.test(value)) {
    await dependencies.settings.putLLM({...config,egress_enabled:value.startsWith('开启')});
    return {content:value.startsWith('开启')?'LLM 外发已开启。':'LLM 外发已关闭。设置命令仍可在本机使用。'};
  }
  const option=/^设置(模型|接口地址)为([\s\S]+)$/.exec(value);
  if(option){await dependencies.settings.putLLM({...config,[option[1]==='模型'?'model':'base_url']:option[2].trim()});return {content:'模型连接配置已保存，可继续检查模型连接。'};}
  throw new Error('本地设置命令不完整。');
}
