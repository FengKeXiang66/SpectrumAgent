import type { ExperimentScore } from './api';

export type SampleMode = 'IMAGE' | 'MAPPED' | 'MIXED';
export type SampleRow = {sample_id:string;display_id:string;image_count:number;observations:number;valid:number;
  truth:number|null;prediction:number|null;truth_counts:Record<string,number>;votes:Record<string,number>;
  correct:boolean|null;status:string;reasons:string[]};
export type SampleRole = {total:number;included:number;excluded:number;exclusion_counts:Record<string,number>;
  metrics:ExperimentScore|null;rows:SampleRow[]};
export type SampleView = {revision:number;applicable:boolean;unavailable_reason?:string|null;form_id:string|null;
  sources:{source_ref:string;name:string;roles:string[]}[];
  definition:{mode:SampleMode;minimum_valid:number;mapping:{source_ref:string;sample_id:string}[]}|null;
  report:{status:string;protocol:string;reason?:string;total_objects:number|null;roles:Record<string,SampleRole>;
    pixel_metrics:Record<string,Pick<ExperimentScore,'n'|'accuracy'|'macro_f1'|'evaluation_unit'|'purpose'>>;
    truth_basis?:string;observation_note?:string;macro_definition?:string}|null};

export function sampleCommand(body:{experiment_id:string;expected_revision:number;mode:SampleMode;minimum_valid:number;
  form_id:string;mapping:{source_ref:string;sample_id:string}[];mapping_csv?:string}) {
  if (!['IMAGE','MAPPED','MIXED'].includes(body.mode)) throw new Error('请明确选择实物定义。');
  if (!Number.isInteger(body.minimum_valid)||body.minimum_valid<1||body.minimum_valid>1000000)
    throw new Error('有效观测阈值必须为1至1000000之间的整数。');
  if (body.mode==='MAPPED'&&!body.mapping_csv&&(!body.mapping.length||body.mapping.some(row=>!row.sample_id.trim())))
    throw new Error('请填写完整分组表，或选择CSV。');
  return '提交实物评价定义 '+JSON.stringify(body);
}

export const sampleReasons:Record<string,string>={truth_conflict:'真值冲突',split_overlap:'实物跨训练与测试',
  insufficient:'有效观测不足',tie:'预测平票',truth_unavailable:'没有保存的真值观测'};
