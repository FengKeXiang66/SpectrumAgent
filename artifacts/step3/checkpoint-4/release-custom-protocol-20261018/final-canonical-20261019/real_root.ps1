$RealData='C:\Users\Administrator\AppData\Local\SpectrumAgent'
$RealProgram='C:\Users\Administrator\AppData\Local\Programs\SpectrumAgent'
function Assert-RealLineage([string]$Label){
 $source=$RealData+'\logs\shell-20261019.log'
 $item=Get-Item -LiteralPath $source
 $bytes=[IO.File]::ReadAllBytes($source)
 $first=[Text.Encoding]::UTF8.GetString($bytes).Split("`n")[0]|ConvertFrom-Json
 if($first.timestamp -cne '2026-10-19T01:47:35.930Z'){throw ('REAL_ROOT_LINEAGE_MISMATCH: '+$first.timestamp)}
 $target=Join-Path $PSScriptRoot ($Label+'-live-shell-source.log')
 if(Test-Path -LiteralPath $target){throw 'Lineage snapshot already exists'}
 [IO.File]::WriteAllBytes($target,$bytes)
 [ordered]@{source=$source;source_root=$RealData;creation_time_utc=$item.CreationTimeUtc.ToString('o');first_timestamp=$first.timestamp;snapshot=$target;bytes=$bytes.Length;sha256=(Get-FileHash -LiteralPath $target).Hash.ToLowerInvariant();identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name;sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;captured_utc=[DateTime]::UtcNow.ToString('o')}
}
