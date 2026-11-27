/** Old workspace events are navigation hints, never execution requests. */
export function preprocessingPrompt(cubeId: string, current: string): string {
  return current.trim() ? current : `为数据 ${cubeId} 配置预处理。请先确认用于分类训练，还是回归／高级配方；本轮先配置参数。`;
}
