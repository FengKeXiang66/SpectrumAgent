$ErrorActionPreference='Stop'
$mtPath='C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\mt.exe'
$run=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
foreach($entry in @(@('shell','E:\AI_Agent\src-tauri\target\release\spectrum-agent.exe'),@('engine','E:\AI_Agent\src-tauri\target\release\resources\backend\app.exe'))){
    $exePath=$entry[1]
    $manifestPath="E:\AI_Agent\artifacts\step3\staging-reports\$run-$($entry[0]).manifest.xml"
    if(Test-Path -LiteralPath $manifestPath){throw 'Refuse evidence overwrite'}
    $before=(Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
    $inputArg="-inputresource:$exePath;#1"
    $outputArg="-out:$manifestPath"
    Write-Output "& '$mtPath' '$inputArg' '$outputArg'"
    & $mtPath $inputArg $outputArg
    if($LASTEXITCODE -ne 0){throw "RT_MANIFEST extraction failed: $($entry[0])"}
    Get-Content -LiteralPath $manifestPath -Raw
    [xml]$xml=Get-Content -LiteralPath $manifestPath -Raw
    $ns=[Xml.XmlNamespaceManager]::new($xml.NameTable)
    $ns.AddNamespace('v1','urn:schemas-microsoft-com:asm.v1')
    $ns.AddNamespace('v3','urn:schemas-microsoft-com:asm.v3')
    $ns.AddNamespace('win','http://schemas.microsoft.com/SMI/2016/WindowsSettings')
    if($xml.SelectSingleNode('//win:longPathAware',$ns).InnerText -ne 'true'){throw 'longPathAware absent/wrong namespace'}
    if($xml.SelectSingleNode('//v3:requestedExecutionLevel',$ns).level -ne 'asInvoker'){throw 'asInvoker absent'}
    if($xml.SelectSingleNode('//v1:assemblyIdentity[@name="Microsoft.Windows.Common-Controls"]',$ns).version -ne '6.0.0.0'){throw 'Common Controls v6 absent'}
    $after=(Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
    if($before -cne $after){throw 'Extraction subject changed'}
    [ordered]@{exe=$exePath;sha256=$after;manifest=$manifestPath;manifest_sha256=(Get-FileHash -LiteralPath $manifestPath).Hash;longPathAware=$true;asInvoker=$true;commonControlsV6=$true} | ConvertTo-Json
}
$longPaths=Get-ItemPropertyValue -LiteralPath HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled
Write-Output "LongPathsEnabled=$longPaths; over_260_functional_test=UNVERIFIED_VM"
