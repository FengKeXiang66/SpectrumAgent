param([string]$Path,[ValidateSet('GetContent','DeleteSharing')][string]$Mode,[string]$StopFile)
$ErrorActionPreference='Stop'
while(-not(Test-Path -LiteralPath $StopFile)){
 try{
  if($Mode -eq 'GetContent'){$null=Get-Content -LiteralPath $Path -Raw -ErrorAction Stop}
  else{
   $file=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
   try{$reader=[IO.StreamReader]::new($file);$null=$reader.ReadToEnd()}finally{$file.Dispose()}
  }
 }catch{}
}
