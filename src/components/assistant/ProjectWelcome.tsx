import type { AssistantSession } from './useSession';
import { currentProjectName } from './SessionScope';

export default function ProjectWelcome({session, onImport, onEdit, onHistory}: {
  session: AssistantSession; onImport(): void; onEdit(text: string): void; onHistory(): void;
}) {
  const disabled = !session.canSend || !!session.state.pending || !session.projectId;
  return <section className="project-welcome" aria-label="开始本项目的对话">
    <h3>在「{currentProjectName(session)}」中开始</h3>
    <p>数据保存在项目中。同项目的新对话可以继续使用已有数据，无需重新导入。</p>
    <ol className="project-start-steps">
      <li><strong>确认项目</strong><span>左侧切换或新建项目，分别管理不同课题。</span></li>
      <li><strong>准备数据</strong><span>导入新数据，或查看本项目已有数据。</span></li>
      <li><strong>说明目标</strong><span>告诉助手要标注、训练还是预测，再按方案卡逐步确认。</span></li>
    </ol>
    <div className="work-actions">
      <button type="button" disabled={disabled} onClick={onImport}>选择目录导入数据</button>
      <button type="button" disabled={disabled} onClick={() => onEdit('查看已导入的数据')}>查看项目数据</button>
      <button type="button" disabled={disabled} onClick={onHistory}>查看本项目模型与结果</button>
    </div>
    <p className="project-welcome-note">前两个入口会填入对话，发送后执行。继续未完成的步骤，请打开左侧原对话。</p>
  </section>;
}
