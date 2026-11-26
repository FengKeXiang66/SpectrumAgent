import assert from 'node:assert/strict';
import test from 'node:test';
import { parseLabelNames, createLabelsCommand, labelCommandText } from '../src/components/assistant/label-names.ts';

test('chat forms parse names, preserve names with spaces, and send a batch-bound command', () => {
  const names = parseLabelNames('PE、PET，PP; PE\n"hard plastic"');
  assert.deepEqual(names, ['PE', 'PET', 'PP', 'hard plastic']);
  const id = '10000000-0000-4000-8000-000000000001';
  const command = createLabelsCommand(id, 'PE、PET、PP');
  assert.equal(command, `创建导入标签 ${id} ["PE","PET","PP"]`);
  assert.equal(labelCommandText(command), '创建标签：PE、PET、PP');
  assert.equal(labelCommandText('你好'), '你好');
  assert.equal(labelCommandText(`创建导入标签 ${id} invalid`), `创建导入标签 ${id} invalid`);
});

test('invalid names cannot be submitted by the form', () => {
  for (const input of ['', '、，;\n', 'x'.repeat(101), 'bad\tname', Array(101).fill('PE').join(',')])
    assert.throws(() => parseLabelNames(input));
});
