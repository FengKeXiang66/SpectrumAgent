import type { ChatEntry } from './sse.ts';
import type { TaskCard } from './api.ts';
import type { DatasetChoice } from './presentation.ts';
import type { DatasetReference } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';

export type AnnotationChoice = { text:string; selected?:'per_image'|'all'; memberCount?:number;cubeIds?:string[];active:boolean };

// Cards belong to a reply, not to a fixed panel. Scanning full turns also lets
// accepted tasks suppress a redundant mode question in the same reply.
export function annotationChoices(entries:ChatEntry[]):Map<number,AnnotationChoice> {
  const result = new Map<number,AnnotationChoice>();
  const starts = entries.flatMap((entry,index)=>entry.event==='user'?[index]:[]);
  for(let turn=0;turn<starts.length;turn++) {
    const start=starts[turn],end=starts[turn+1]??entries.length;
    const user=entries[start];if(user.event!=='user')continue;
    const rows=entries.slice(start+1,end);
    const prepared=rows.some(row=>row.event==='step'&&row.data.status==='ok'
      && ['annotations.prepare','annotations.prepare_batch'].includes(row.data.tool)
      || row.event==='done'&&!!row.data.annotation_task_id);
    let reply=-1;
    rows.forEach((row,index)=>{if(row.event==='done'||row.event==='clarify'||row.event==='error')reply=index;});
    const replyEntry=rows[reply];
    // Only a server-owned selection payload can create a business choice.
    // Neither prior annotation intent nor words in prose grant a new choice.
    if(reply>=0&&!prepared&&(replyEntry?.event==='done'||replyEntry?.event==='error')
        &&Array.isArray(replyEntry.data.annotation_target_cube_ids)) {
      const nextRows=entries.slice(end+1,starts[turn+2]??entries.length);
      const recordedMode=nextRows.find(row=>row.event==='done'&&!!row.data.annotation_mode);
      const selected=recordedMode?.event==='done'?recordedMode.data.annotation_mode:undefined;
      const confirmation=nextRows
        .find(row=>row.event==='done'&&row.data.annotation_mode===selected);
      const count=confirmation?.event==='done'?confirmation.data.annotation_member_count:undefined;
      const cubeIds=replyEntry.data.annotation_target_cube_ids;
      result.set(start+1+reply,{text:user.data.content,selected,
        ...(Array.isArray(cubeIds)?{cubeIds:[...cubeIds]}:{}),
        ...(typeof count==='number'&&Number.isInteger(count)&&count>0?{memberCount:count}:{}),active:end===entries.length});
    }
  }
  return result;
}

export function taskPositions(entries:ChatEntry[],cards:TaskCard[]):Map<number,TaskCard[]> {
  const positions=new Map<number,TaskCard[]>();
  for(const card of cards) {
    let anchor=entries.findIndex(entry=>entry.event==='done'&&entry.data.annotation_task_id===card.taskId
      || entry.event==='step'&&entry.data.result_summary.status==='accepted'&&entry.data.result_summary.task_id===card.taskId);
    if(anchor<0&&card.requestId)anchor=entries.findIndex(entry=>entry.requestId===card.requestId);
    if(anchor<0)continue; // Load its actual history first; never invent a position.
    anchor=replyPosition(entries,anchor);
    positions.set(anchor,[...(positions.get(anchor)??[]),card]);
  }
  return positions;
}

export function replyPosition(entries:ChatEntry[],start:number):number {
  let anchor=start;
  for(let next=start+1;next<entries.length&&entries[next].event!=='user';next++) {
    if(entries[next].event==='done'||entries[next].event==='clarify')anchor=next;
  }
  return anchor;
}

export function choiceScope(text:string,records:DatasetReference[],choices:DatasetChoice[],canvas?:string,requireExplicit=false) {
  if(/除了?|排除|不对|不要(?:对|处理|标注)|不(?:生成|标注)/.test(text))return null;
  const ids = new Set<string>();
  const refs:number[]=[];
  let invalidRange=false;
  const referenceText=text.replace(/(?<![a-zA-Z0-9_-])[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?![a-zA-Z0-9_-])/gi,' ');
  const remainder=referenceText.replace(/(?<![a-zA-Z0-9_-])D(\d+)\s*[-–—~～至到]\s*D?(\d+)(?![a-zA-Z0-9_-])/gi,(_,a:string,b:string)=>{
    const start=Number(a),end=Number(b);
    if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<1||end<start||end-start+1>choices.length)invalidRange=true;
    else for(let index=start;index<=end;index++)refs.push(index);
    return ' ';
  });
  if(invalidRange||/(?<![a-zA-Z0-9_-])D\d+\s*[-–—~～至到]/i.test(remainder))return null;
  refs.push(...[...remainder.matchAll(/(?<![a-zA-Z0-9_-])D(\d+)(?![a-zA-Z0-9_-])/gi)].map(ref=>Number(ref[1])));
  for(const ref of refs) {
    const match=choices.find(item=>item.index===ref);
    if(!match)return null;
    ids.add(match.id);
  }
  for(const record of records)if(text.includes(record.id)||text.includes(displayName(record)))ids.add(record.id);
  if(/当前(?:这)?(?:张|幅|图|样品|数据)/.test(text)) {
    if(!canvas)return null;
    ids.add(canvas);
  }
  if(!ids.size&&/第[一二三四五六七八九十百\d]+[个张项]|除了?|排除/.test(text))return null;
  if(!ids.size) {
    if(requireExplicit&&!/^(?:所有|全部)(?:已导入的?|的)?(?:数据(?:集)?|图片|图像|样品)[。！!\s]*$/.test(text.trim()))return null;
    const target=/(?:对|给|为)(.+?)(?:进行|开始|生成|标注)/.exec(text)?.[1];
    if(target&&!/^(?:所有|全部|已|导入|的|数据|集|图片|图像|样品|统一|批量|\s)+$/.test(target))return null;
  }
  const selected=ids.size?records.filter(row=>ids.has(row.id)):records;
  if(ids.size&&selected.length!==ids.size)return null;
  return {cubeIds:selected.map(row=>row.id),label:ids.size?selected.map(displayName).join('、'):'全部已导入数据'};
}
