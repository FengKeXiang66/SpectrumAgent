$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'SpectrumAgent'
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$out="E:\AI_Agent\artifacts\step3\checkpoint-4\explorer-context-$stamp"
New-Item -ItemType Directory -Path $out | Out-Null
$hsRaw=[IO.File]::ReadAllText((Join-Path $root 'run\handshake.json'))
$hs=$hsRaw|ConvertFrom-Json
$token=$hs.token
$hs.token='[REDACTED]'
$hs|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $out 'handshake-redacted.json') -Encoding utf8
$records=@()
foreach($name in @('shell-20261018.log','engine-20261018.jsonl')){
  $path=Join-Path $root ('logs\'+$name)
  $bytes=[IO.File]::ReadAllBytes($path)
  $raw=[Text.Encoding]::UTF8.GetString($bytes)
  $hits=if($token -and $raw.Contains($token)){1}else{0}
  $bearer=$raw.IndexOf('Authorization: Bearer',[StringComparison]::OrdinalIgnoreCase) -ge 0
  if($hits -or $bearer){throw 'Original source token scan failed; refusing raw archive'}
  [IO.File]::WriteAllBytes((Join-Path $out $name),$bytes)
  $records+=@{source=$path;bytes=$bytes.Length;sha256=(Get-FileHash -LiteralPath $path).Hash;actual_token_samples=1;exact_token_hits=$hits;authorization_bearer=$bearer}
}
$records|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $out 'source-audit.json') -Encoding utf8
Write-Output $out
