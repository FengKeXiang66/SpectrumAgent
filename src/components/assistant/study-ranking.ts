import type { StudyCandidate } from './api';

export function topCandidates(rows:StudyCandidate[], recommended:number) {
  const top = rows.slice(0,10);
  const recommendation = rows.find(row=>row.id===recommended);
  if (recommendation && !top.includes(recommendation)) return [...top.slice(0,9),recommendation];
  return top;
}

export const candidateCommand = (studyId:string, id:number) => '采用候选 '+id+'新建正式训练 '+studyId;

export function filterCandidates(rows:StudyCandidate[], name:string, search:string, eligible:boolean, threshold:number) {
  const query = search.trim().toLowerCase();
  return rows.filter(row=>(!name||row.name===name)
    && (!query || [row.id,row.name,row.n_components,row.error??''].some(value=>String(value).toLowerCase().includes(query)))
    && (!eligible || row.cv_f1!==undefined && row.cv_f1>=threshold));
}

export const candidatePageSize = 20;

export function candidatePage(rows:StudyCandidate[], page:number) {
  return rows.slice(page*candidatePageSize,(page+1)*candidatePageSize);
}
