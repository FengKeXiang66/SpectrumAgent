$ErrorActionPreference='Stop'
$out=$PSScriptRoot
$source='E:\AI_Agent\src-tauri\target\release\bundle\nsis\SpectrumAgent_0.1.0_x64-setup.exe'
$destination='E:\AI_Agent\artifacts\step4\setup.exe'
$expected='d849253611c1ac985cb08a60a7073e17ed6c89b74e8230532d0c3d2157cc8107'
$record=Join-Path $out 'step4-copy-record.json'
if(Test-Path -LiteralPath $record){throw 'Do not overwrite copy record'}
$before=if(Test-Path -LiteralPath $destination){[ordered]@{sha256=(Get-FileHash -LiteralPath $destination).Hash.ToLowerInvariant();bytes=(Get-Item -LiteralPath $destination).Length}}else{$null}
if((Get-Item -LiteralPath $source).Length -ne 287156790 -or (Get-FileHash -LiteralPath $source).Hash.ToLowerInvariant() -cne $expected){throw 'Delivery setup mismatch'}
Copy-Item -LiteralPath $source -Destination $destination -Force
$sha=(Get-FileHash -LiteralPath $destination).Hash.ToLowerInvariant()
if($sha -cne $expected -or (Get-Item -LiteralPath $destination).Length -ne 287156790){throw 'Copied delivery bytes mismatch'}
[ordered]@{copied_utc=[DateTime]::UtcNow.ToString('o');source=$source;destination=$destination;source_sha256=$expected;destination_sha256=$sha;source_bytes=287156790;destination_bytes=(Get-Item -LiteralPath $destination).Length;previous_destination=$before;delivery_shell_sha256='22a13e6a4d2ec88cf58fa349aad7f22e61fa11331adca11e11eec9c781f73471';repro_29a_is_delivery=$false}|ConvertTo-Json -Depth 5|Tee-Object -FilePath $record
$webview='E:\AI_Agent\src-tauri\target\.tauri\x64\MicrosoftEdgeWebview2Setup.exe'
if(-not (Test-Path -LiteralPath $webview)){
 $webview=(Get-Content -LiteralPath (Join-Path $out 'signature-three-way.json') -Raw|ConvertFrom-Json|Where-Object {$_.role -eq 'webview2'}).path
}
$paths=@($source,'E:\AI_Agent\src-tauri\target\release\spectrum-agent.exe','E:\AI_Agent\src-tauri\target\release\resources\backend\app.exe',$webview)
$signatures=foreach($p in $paths){$s=Get-AuthenticodeSignature -LiteralPath $p;[ordered]@{path=$p;bytes=(Get-Item -LiteralPath $p).Length;sha256=(Get-FileHash -LiteralPath $p).Hash.ToLowerInvariant();status=[string]$s.Status;signer_subject=if($s.SignerCertificate){$s.SignerCertificate.Subject}else{$null}}}
$signatures|ConvertTo-Json -Depth 5|Tee-Object -FilePath (Join-Path $out 'delivery-signature-three-way.json')
