$ErrorActionPreference='Stop'
$mtPath='C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\mt.exe'
$program='E:\AI_Agent\src-tauri\target\repro-check\release'
$run=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
foreach($entry in @(@('repro-shell',(Join-Path $program 'spectrum-agent.exe')),@('repro-engine',(Join-Path $program 'resources\backend\app.exe')))){
 $exePath=$entry[1]
 $manifestPath="E:\AI_Agent\artifacts\step3\staging-reports\$run-$($entry[0]).manifest.xml"
 if(Test-Path -LiteralPath $manifestPath){throw 'Refuse evidence overwrite'}
 $before=(Get-FileHash -LiteralPath $exePath).Hash
 $inputArg="-inputresource:$exePath;#1"
 $outputArg="-out:$manifestPath"
 Write-Output "& '$mtPath' '$inputArg' '$outputArg'"
 & $mtPath $inputArg $outputArg
 if($LASTEXITCODE -ne 0){throw 'Installed RT_MANIFEST extraction failed'}
 Get-Content -LiteralPath $manifestPath -Raw
 [xml]$xml=Get-Content -LiteralPath $manifestPath -Raw
 $ns=[Xml.XmlNamespaceManager]::new($xml.NameTable)
 $ns.AddNamespace('v1','urn:schemas-microsoft-com:asm.v1');$ns.AddNamespace('v3','urn:schemas-microsoft-com:asm.v3');$ns.AddNamespace('win','http://schemas.microsoft.com/SMI/2016/WindowsSettings')
 if($xml.SelectSingleNode('//win:longPathAware',$ns).InnerText -ne 'true'){throw 'Wrong/missing longPathAware namespace'}
 if($xml.SelectSingleNode('//v3:requestedExecutionLevel',$ns).level -ne 'asInvoker'){throw 'asInvoker missing'}
 if($xml.SelectSingleNode('//v1:assemblyIdentity[@name="Microsoft.Windows.Common-Controls"]',$ns).version -ne '6.0.0.0'){throw 'CommonControls6 missing'}
 $after=(Get-FileHash -LiteralPath $exePath).Hash
 if($before -cne $after){throw 'Extraction object changed'}
 [ordered]@{exe=$exePath;sha256=$after;manifest=$manifestPath;manifest_sha256=(Get-FileHash -LiteralPath $manifestPath).Hash;longPathAware=$true;asInvoker=$true;commonControlsV6=$true}|ConvertTo-Json
}
