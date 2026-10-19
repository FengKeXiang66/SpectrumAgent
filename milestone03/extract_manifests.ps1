$ErrorActionPreference='Stop'
$root='E:\AI_Agent'
$mt='C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\mt.exe'
$program="$root\src-tauri\target\milestone03\release"
$evidence="$root\milestone03\evidence\P4"
foreach($entry in @(@('shell',"$program\spectrum-agent.exe"),@('engine',"$program\resources\backend\app.exe"))){
  $exe=$entry[1]
  $out="$evidence\$($entry[0]).manifest.xml"
  if(Test-Path -LiteralPath $out){throw 'Refuse manifest overwrite'}
  $before=(Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant()
  & $mt "-inputresource:$exe;#1" "-out:$out"
  if($LASTEXITCODE -ne 0){throw 'RT_MANIFEST extraction failed'}
  [xml]$xml=Get-Content -LiteralPath $out -Raw
  $ns=[Xml.XmlNamespaceManager]::new($xml.NameTable)
  $ns.AddNamespace('v1','urn:schemas-microsoft-com:asm.v1')
  $ns.AddNamespace('v3','urn:schemas-microsoft-com:asm.v3')
  $ns.AddNamespace('win','http://schemas.microsoft.com/SMI/2016/WindowsSettings')
  if($xml.SelectSingleNode('//win:longPathAware',$ns).InnerText -ne 'true'){throw 'Missing longPathAware'}
  if($xml.SelectSingleNode('//v3:requestedExecutionLevel',$ns).level -ne 'asInvoker'){throw 'Missing asInvoker'}
  if($xml.SelectSingleNode('//v1:assemblyIdentity[@name="Microsoft.Windows.Common-Controls"]',$ns).version -ne '6.0.0.0'){throw 'Missing CommonControls6'}
  if($before -ne (Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant()){throw 'Extraction mutated executable'}
  @{exe=$exe;sha256=$before;manifest=$out;manifest_sha256=(Get-FileHash -LiteralPath $out).Hash.ToLowerInvariant();longPathAware=$true;asInvoker=$true;commonControlsV6=$true;functional_over_260='缓测'} | ConvertTo-Json | Set-Content -LiteralPath "$evidence\$($entry[0])-manifest-binding.json" -Encoding UTF8
  Get-Content -LiteralPath "$evidence\$($entry[0])-manifest-binding.json"
}
