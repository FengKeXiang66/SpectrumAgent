import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

const root = String.raw`E:\AI_Agent`;
const evidence = path.join(root, 'artifacts/step3/checkpoint-4/release-custom-protocol-20261018');
const url = 'https://raw.githubusercontent.com/tauri-apps/tauri/tauri-cli-v2.12.3/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi';
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
assert.notEqual(process.env.NODE_TLS_REJECT_UNAUTHORIZED, '0');
const pkg = JSON.parse(await fs.readFile(path.join(root, 'node_modules/@tauri-apps/cli-win32-x64-msvc/package.json'), 'utf8'));
assert.equal(pkg.version, '2.12.3');
const upstreamPath = path.join(evidence, 'upstream-installer.nsi');
const nativePath = path.join(root, 'node_modules/@tauri-apps/cli-win32-x64-msvc/cli.win32-x64-msvc.node');
const native = await fs.readFile(nativePath);
const signature = Buffer.from('Unicode true\r\nManifestDPIAware true\r\n');
const offset = native.indexOf(signature);
assert.ok(offset >= 0);
assert.equal(native.indexOf(signature, offset + 1), -1);
const end = native.indexOf(0, offset);
assert.ok(end > offset);
const upstream = native.subarray(offset, end);
const ending = '  CreateShortcut "$DESKTOP\\${PRODUCTNAME}.lnk" "$INSTDIR\\${MAINBINARYNAME}.exe"\r\n  !insertmacro SetLnkAppUserModelId "$DESKTOP\\${PRODUCTNAME}.lnk"\r\nFunctionEnd\r\n';
assert.ok(upstream.toString('utf8').endsWith(ending), 'Complete installer template boundary must match its final function');
await fs.writeFile(upstreamPath, upstream, { flag: 'wx' });
assert.equal(native.indexOf(upstream, offset + 1), -1, 'Expected one complete embedded template');
const source = upstream.toString('utf8');
const oldLine = '      StrCpy $INSTDIR "$LOCALAPPDATA\\${PRODUCTNAME}"';
const newLine = '      StrCpy $INSTDIR "$LOCALAPPDATA\\Programs\\${PRODUCTNAME}"';
assert.equal(source.split(oldLine).length - 1, 1, 'Expected exactly one currentUser install-directory line');
const modified = source.replace(oldLine, newLine);
const before = source.split('\n'), after = modified.split('\n');
const differences = before.flatMap((line, index) => line === after[index] ? [] : [index + 1]);
assert.equal(before.length, after.length);
assert.equal(differences.length, 1);
const templateDir = path.join(root, 'src-tauri/nsis');
await fs.mkdir(templateDir, { recursive: true });
const target = path.join(templateDir, 'installer.nsi');
const modifiedBytes = Buffer.from(modified, 'utf8');
await fs.writeFile(target, modifiedBytes, { flag: 'wx' });
const line = differences[0];
const diff = `--- upstream/tauri-cli-v2.12.3/installer.nsi\n+++ src-tauri/nsis/installer.nsi\n@@ -${line},1 +${line},1 @@\n-${oldLine}\n+${newLine}\n`;
await fs.writeFile(path.join(evidence, 'installer-single-line.diff'), diff, { flag: 'wx' });
const record = {reference_url:url, source:'exact installed CLI embedded installer.nsi bytes; online GET failed with ECONNRESET',
  online_full_byte_comparison:'UNVERIFIED', cli_version:pkg.version, upstream_bytes:upstream.length,
  upstream_sha256:sha(upstream), native_cli_path:nativePath, native_cli_sha256:sha(native),
  full_upstream_template_embedded_byte_offset:offset, template_path:target,
  template_bytes:modifiedBytes.length, template_sha256:sha(modifiedBytes),
  changed_line:line, changed_lines:1, old_line:oldLine, new_line:newLine,
  perMachine_unchanged:true, placeholder_guard_unchanged:true, uninstaller_unchanged:true,
  tls_verification_disabled:false};
await fs.writeFile(path.join(evidence, 'template-provenance.json'), JSON.stringify(record,null,2)+'\n', { flag:'wx' });
console.log(JSON.stringify(record,null,2));
