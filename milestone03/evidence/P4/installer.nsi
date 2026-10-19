Unicode true
ManifestDPIAware true
; Add in `dpiAwareness` `PerMonitorV2` to manifest for Windows 10 1607+ (note this should not affect lower versions since they should be able to ignore this and pick up `dpiAware` `true` set by `ManifestDPIAware true`)
; Currently undocumented on NSIS's website but is in the Docs folder of source tree, see
; https://github.com/kichik/nsis/blob/5fc0b87b819a9eec006df4967d08e522ddd651c9/Docs/src/attributes.but#L286-L300
; https://github.com/tauri-apps/tauri/pull/10106
ManifestDPIAwareness PerMonitorV2

!if "lzma" == "none"
  SetCompress off
!else
  ; Set the compression algorithm. We default to LZMA.
  SetCompressor /SOLID "lzma"
!endif

; Keep above !include to stay ahead of any plugin command
; see https://github.com/tauri-apps/tauri/pull/15422#discussion_r3289239624

!include MUI2.nsh
!include FileFunc.nsh
!include x64.nsh
!include WordFunc.nsh
!include "utils.nsh"
!include "FileAssociation.nsh"
!include "Win\COM.nsh"
!include "Win\Propkey.nsh"
!include "Win\RestartManager.nsh"
!include "StrFunc.nsh"
${StrCase}
${StrLoc}


!define WEBVIEW2APPGUID "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

!define MANUFACTURER "spectrumagent"
!define PRODUCTNAME "SpectrumAgent"
!define VERSION "0.1.1"
!define VERSIONWITHBUILD "0.1.1.0"
!define HOMEPAGE ""
!define INSTALLMODE "currentUser"
!define LICENSE ""
!define INSTALLERICON ""
!define SIDEBARIMAGE ""
!define HEADERIMAGE ""
!define UNINSTALLERICON ""
!define UNINSTALLERHEADERIMAGE ""
!define MAINBINARYNAME "spectrum-agent"
!define MAINBINARYSRCPATH "E:\AI_Agent\src-tauri\target\milestone03\release\spectrum-agent.exe"
!define BUNDLEID "com.spectrumagent.desktop"
!define COPYRIGHT ""
!define OUTFILE "nsis-output.exe"
!define ARCH "x64"
!define ADDITIONALPLUGINSPATH "E:\AI_Agent\src-tauri\target\milestone03\.tauri\NSIS\Plugins\x86-unicode\additional"
!define ALLOWDOWNGRADES "true"
!define DISPLAYLANGUAGESELECTOR "false"
!define INSTALLWEBVIEW2MODE "offlineInstaller"
!define WEBVIEW2INSTALLERARGS "/silent"
!define WEBVIEW2BOOTSTRAPPERPATH ""
!define WEBVIEW2INSTALLERPATH "E:\AI_Agent\src-tauri\target\milestone03\.tauri\x64\35871e19-d11b-432d-9d1e-7be0ff286540\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
!define MINIMUMWEBVIEW2VERSION ""
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCTNAME}"
!define MANUKEY "Software\${MANUFACTURER}"
!define MANUPRODUCTKEY "${MANUKEY}\${PRODUCTNAME}"
!define UNINSTALLERSIGNCOMMAND ""
!define ESTIMATEDSIZE "260842"
!define STARTMENUFOLDER ""

Var PassiveMode
Var UpdateMode
Var NoShortcutMode
Var WixMode
Var OldMainBinaryName

Name "${PRODUCTNAME}"
BrandingText "${COPYRIGHT}"
OutFile "${OUTFILE}"

; We don't actually use this value as default install path,
; it's just for nsis to append the product name folder in the directory selector
; https://nsis.sourceforge.io/Reference/InstallDir
!define PLACEHOLDER_INSTALL_DIR "placeholder\${PRODUCTNAME}"
InstallDir "${PLACEHOLDER_INSTALL_DIR}"

VIProductVersion "${VERSIONWITHBUILD}"
VIAddVersionKey "ProductName" "${PRODUCTNAME}"
VIAddVersionKey "FileDescription" "${PRODUCTNAME}"
VIAddVersionKey "LegalCopyright" "${COPYRIGHT}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"

# additional plugins
!addplugindir "${ADDITIONALPLUGINSPATH}"

; Uninstaller signing command
!if "${UNINSTALLERSIGNCOMMAND}" != ""
  !uninstfinalize '${UNINSTALLERSIGNCOMMAND}'
!endif

; Handle install mode, `perUser`, `perMachine` or `both`
!if "${INSTALLMODE}" == "perMachine"
  RequestExecutionLevel admin
!endif

!if "${INSTALLMODE}" == "currentUser"
  RequestExecutionLevel user
!endif

!if "${INSTALLMODE}" == "both"
  !define MULTIUSER_MUI
  !define MULTIUSER_INSTALLMODE_INSTDIR "${PRODUCTNAME}"
  !define MULTIUSER_INSTALLMODE_COMMANDLINE
  !if "${ARCH}" == "x64"
    !define MULTIUSER_USE_PROGRAMFILES64
  !else if "${ARCH}" == "arm64"
    !define MULTIUSER_USE_PROGRAMFILES64
  !endif
  !define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_KEY "${UNINSTKEY}"
  !define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_VALUENAME "CurrentUser"
  !define MULTIUSER_INSTALLMODEPAGE_SHOWUSERNAME
  !define MULTIUSER_INSTALLMODE_FUNCTION RestorePreviousInstallLocation
  !define MULTIUSER_EXECUTIONLEVEL Highest
  !include MultiUser.nsh
!endif

; Installer icon
!if "${INSTALLERICON}" != ""
  !define MUI_ICON "${INSTALLERICON}"
!endif

; Installer sidebar image
!if "${SIDEBARIMAGE}" != ""
  !define MUI_WELCOMEFINISHPAGE_BITMAP "${SIDEBARIMAGE}"
!endif

; Enable header images for installer and uninstaller pages when either image is configured.
!if "${HEADERIMAGE}" != ""
  !define MUI_HEADERIMAGE
!else if "${UNINSTALLERHEADERIMAGE}" != ""
  !define MUI_HEADERIMAGE
!endif

; Installer header image
!if "${HEADERIMAGE}" != ""
  !define MUI_HEADERIMAGE_BITMAP "${HEADERIMAGE}"
!endif

; Uninstaller header image
!if "${UNINSTALLERHEADERIMAGE}" != ""
  !define MUI_HEADERIMAGE_UNBITMAP "${UNINSTALLERHEADERIMAGE}"
!endif

; Uninstaller icon
!if "${UNINSTALLERICON}" != ""
  !define MUI_UNICON "${UNINSTALLERICON}"
!endif

; Define registry key to store installer language
!define MUI_LANGDLL_REGISTRY_ROOT "HKCU"
!define MUI_LANGDLL_REGISTRY_KEY "${MANUPRODUCTKEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "Installer Language"

; Installer pages, must be ordered as they appear
; 1. Welcome Page
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
!insertmacro MUI_PAGE_WELCOME

; 2. License Page (if defined)
!if "${LICENSE}" != ""
  !define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
  !insertmacro MUI_PAGE_LICENSE "${LICENSE}"
!endif

; 3. Install mode (if it is set to `both`)
!if "${INSTALLMODE}" == "both"
  !define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
  !insertmacro MULTIUSER_PAGE_INSTALLMODE
!endif

; 4. Custom page to ask user if he wants to reinstall/uninstall
;    only if a previous installation was detected
Var ReinstallPageCheck
Page custom PageReinstall PageLeaveReinstall
Function PageReinstall
  ; Uninstall previous WiX installation if exists.
  ;
  ; A WiX installer stores the installation info in registry
  ; using a UUID and so we have to loop through all keys under
  ; `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`
  ; and check if `DisplayName` and `Publisher` keys match ${PRODUCTNAME} and ${MANUFACTURER}
  ;
  ; This has a potential issue that there maybe another installation that matches
  ; our ${PRODUCTNAME} and ${MANUFACTURER} but wasn't installed by our WiX installer,
  ; however, this should be fine since the user will have to confirm the uninstallation
  ; and they can chose to abort it if doesn't make sense.
  StrCpy $0 0
  wix_loop:
    EnumRegKey $1 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" $0
    StrCmp $1 "" wix_loop_done ; Exit loop if there is no more keys to loop on
    IntOp $0 $0 + 1
    ReadRegStr $R0 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "DisplayName"
    ReadRegStr $R1 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "Publisher"
    StrCmp "$R0$R1" "${PRODUCTNAME}${MANUFACTURER}" 0 wix_loop
    ReadRegStr $R0 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1" "UninstallString"
    ${StrCase} $R1 $R0 "L"
    ${StrLoc} $R0 $R1 "msiexec" ">"
    StrCmp $R0 0 0 wix_loop_done
    StrCpy $WixMode 1
    StrCpy $R6 "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$1"
    Goto compare_version
  wix_loop_done:

  ; Check if there is an existing installation, if not, abort the reinstall page
  ReadRegStr $R0 SHCTX "${UNINSTKEY}" ""
  ReadRegStr $R1 SHCTX "${UNINSTKEY}" "UninstallString"
  ${IfThen} "$R0$R1" == "" ${|} Abort ${|}

  ; Compare this installar version with the existing installation
  ; and modify the messages presented to the user accordingly
  compare_version:
  StrCpy $R4 "$(older)"
  ${If} $WixMode = 1
    ReadRegStr $R0 HKLM "$R6" "DisplayVersion"
  ${Else}
    ReadRegStr $R0 SHCTX "${UNINSTKEY}" "DisplayVersion"
  ${EndIf}
  ${IfThen} $R0 == "" ${|} StrCpy $R4 "$(unknown)" ${|}

  nsis_tauri_utils::SemverCompare "${VERSION}" $R0
  Pop $R0
  ; Reinstalling the same version
  ${If} $R0 = 0
    StrCpy $R1 "$(alreadyInstalledLong)"
    StrCpy $R2 "$(addOrReinstall)"
    StrCpy $R3 "$(uninstallApp)"
    !insertmacro MUI_HEADER_TEXT "$(alreadyInstalled)" "$(chooseMaintenanceOption)"
  ; Upgrading
  ${ElseIf} $R0 = 1
    StrCpy $R1 "$(olderOrUnknownVersionInstalled)"
    StrCpy $R2 "$(uninstallBeforeInstalling)"
    StrCpy $R3 "$(dontUninstall)"
    !insertmacro MUI_HEADER_TEXT "$(alreadyInstalled)" "$(choowHowToInstall)"
  ; Downgrading
  ${ElseIf} $R0 = -1
    StrCpy $R1 "$(newerVersionInstalled)"
    StrCpy $R2 "$(uninstallBeforeInstalling)"
    !if "${ALLOWDOWNGRADES}" == "true"
      StrCpy $R3 "$(dontUninstall)"
    !else
      StrCpy $R3 "$(dontUninstallDowngrade)"
    !endif
    !insertmacro MUI_HEADER_TEXT "$(alreadyInstalled)" "$(choowHowToInstall)"
  ${Else}
    Abort
  ${EndIf}

  ; Skip showing the page if passive
  ;
  ; Note that we don't call this earlier at the beginning
  ; of this function because we need to populate some variables
  ; related to current installed version if detected and whether
  ; we are downgrading or not.
  ${If} $PassiveMode = 1
    Call PageLeaveReinstall
  ${Else}
    nsDialogs::Create 1018
    Pop $R4
    ${IfThen} $(^RTL) = 1 ${|} nsDialogs::SetRTL $(^RTL) ${|}

    ${NSD_CreateLabel} 0 0 100% 24u $R1
    Pop $R1

    ${NSD_CreateRadioButton} 30u 50u -30u 8u $R2
    Pop $R2
    ${NSD_OnClick} $R2 PageReinstallUpdateSelection

    ${NSD_CreateRadioButton} 30u 70u -30u 8u $R3
    Pop $R3
    ; Disable this radio button if downgrading and downgrades are disabled
    !if "${ALLOWDOWNGRADES}" == "false"
      ${IfThen} $R0 = -1 ${|} EnableWindow $R3 0 ${|}
    !endif
    ${NSD_OnClick} $R3 PageReinstallUpdateSelection

    ; Check the first radio button if this the first time
    ; we enter this page or if the second button wasn't
    ; selected the last time we were on this page
    ${If} $ReinstallPageCheck <> 2
      SendMessage $R2 ${BM_SETCHECK} ${BST_CHECKED} 0
    ${Else}
      SendMessage $R3 ${BM_SETCHECK} ${BST_CHECKED} 0
    ${EndIf}

    ${NSD_SetFocus} $R2
    nsDialogs::Show
  ${EndIf}
FunctionEnd
Function PageReinstallUpdateSelection
  ${NSD_GetState} $R2 $R1
  ${If} $R1 == ${BST_CHECKED}
    StrCpy $ReinstallPageCheck 1
  ${Else}
    StrCpy $ReinstallPageCheck 2
  ${EndIf}
FunctionEnd
Function PageLeaveReinstall
  ${NSD_GetState} $R2 $R1

  ; If migrating from Wix, always uninstall
  ${If} $WixMode = 1
    Goto reinst_uninstall
  ${EndIf}

  ; In update mode, always proceeds without uninstalling
  ${If} $UpdateMode = 1
    Goto reinst_done
  ${EndIf}

  ; $R0 holds whether same(0)/upgrading(1)/downgrading(-1) version
  ; $R1 holds the radio buttons state:
  ;   1 => first choice was selected
  ;   0 => second choice was selected
  ${If} $R0 = 0 ; Same version, proceed
    ${If} $R1 = 1              ; User chose to add/reinstall
      Goto reinst_done
    ${Else}                    ; User chose to uninstall
      Goto reinst_uninstall
    ${EndIf}
  ${ElseIf} $R0 = 1 ; Upgrading
    ${If} $R1 = 1              ; User chose to uninstall
      Goto reinst_uninstall
    ${Else}
      Goto reinst_done         ; User chose NOT to uninstall
    ${EndIf}
  ${ElseIf} $R0 = -1 ; Downgrading
    ${If} $R1 = 1              ; User chose to uninstall
      Goto reinst_uninstall
    ${Else}
      Goto reinst_done         ; User chose NOT to uninstall
    ${EndIf}
  ${EndIf}

  reinst_uninstall:
    HideWindow
    ClearErrors

    ${If} $WixMode = 1
      ReadRegStr $R1 HKLM "$R6" "UninstallString"
      ExecWait '$R1' $0
    ${Else}
      ReadRegStr $4 SHCTX "${MANUPRODUCTKEY}" ""
      ReadRegStr $R1 SHCTX "${UNINSTKEY}" "UninstallString"
      ${IfThen} $UpdateMode = 1 ${|} StrCpy $R1 "$R1 /UPDATE" ${|} ; append /UPDATE
      ${IfThen} $PassiveMode = 1 ${|} StrCpy $R1 "$R1 /P" ${|} ; append /P
      StrCpy $R1 "$R1 _?=$4" ; append uninstall directory
      ExecWait '$R1' $0
    ${EndIf}

    BringToFront

    ${IfThen} ${Errors} ${|} StrCpy $0 2 ${|} ; ExecWait failed, set fake exit code

    ${If} $0 <> 0
    ${OrIf} ${FileExists} "$INSTDIR\${MAINBINARYNAME}.exe"
      ; User cancelled wix uninstaller? return to select un/reinstall page
      ${If} $WixMode = 1
      ${AndIf} $0 = 1602
        Abort
      ${EndIf}

      ; User cancelled NSIS uninstaller? return to select un/reinstall page
      ${If} $0 = 1
        Abort
      ${EndIf}

      ; Other errors? show generic error message and return to select un/reinstall page
      MessageBox MB_ICONEXCLAMATION "$(unableToUninstall)"
      Abort
    ${EndIf}

    ; The NSIS uninstaller was run in place (`_?=`), so it cannot delete itself
    ; and the install directory, clean them up here once the uninstall succeeded
    ; https://nsis.sourceforge.io/Docs/Chapter3.html#:~:text=path%20contains%20spaces.-,3.2.3%20Examples,-installer.exe%20/NCRC
    ${If} $WixMode = 0
    ${AndIf} $4 != ""
      Delete "$4\uninstall.exe"
      RMDir "$4"
    ${EndIf}
  reinst_done:
FunctionEnd

; 5. Choose install directory page
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
!insertmacro MUI_PAGE_DIRECTORY

; 6. Start menu shortcut page
Var AppStartMenuFolder
!if "${STARTMENUFOLDER}" != ""
  !define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
  !define MUI_STARTMENUPAGE_DEFAULTFOLDER "${STARTMENUFOLDER}"
!else
  !define MUI_PAGE_CUSTOMFUNCTION_PRE Skip
!endif
!insertmacro MUI_PAGE_STARTMENU Application $AppStartMenuFolder

; 7. Installation page
!insertmacro MUI_PAGE_INSTFILES

; 8. Finish page
;
; Don't auto jump to finish page after installation page,
; because the installation page has useful info that can be used debug any issues with the installer.
!define MUI_FINISHPAGE_NOAUTOCLOSE
; Use show readme button in the finish page as a button create a desktop shortcut
!define MUI_FINISHPAGE_SHOWREADME
!define MUI_FINISHPAGE_SHOWREADME_TEXT "$(createDesktop)"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateOrUpdateDesktopShortcut
; Show run app after installation.
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION RunMainBinary
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfPassive
!insertmacro MUI_PAGE_FINISH

Function RunMainBinary
  nsis_tauri_utils::RunAsUser "$INSTDIR\${MAINBINARYNAME}.exe" ""
FunctionEnd

; Uninstaller Pages
; 1. Confirm uninstall page
Var DeleteAppDataCheckbox
Var DeleteAppDataCheckboxState
!define /ifndef WS_EX_LAYOUTRTL         0x00400000
!define MUI_PAGE_CUSTOMFUNCTION_SHOW un.ConfirmShow
Function un.ConfirmShow ; Add add a `Delete app data` check box
  ; $1 inner dialog HWND
  ; $2 window DPI
  ; $3 style
  ; $4 x
  ; $5 y
  ; $6 width
  ; $7 height
  FindWindow $1 "#32770" "" $HWNDPARENT ; Find inner dialog
  System::Call "user32::GetDpiForWindow(p r1) i .r2"
  ${If} $(^RTL) = 1
    StrCpy $3 "${__NSD_CheckBox_EXSTYLE} | ${WS_EX_LAYOUTRTL}"
    IntOp $4 50 * $2
  ${Else}
    StrCpy $3 "${__NSD_CheckBox_EXSTYLE}"
    IntOp $4 0 * $2
  ${EndIf}
  IntOp $5 100 * $2
  IntOp $6 400 * $2
  IntOp $7 25 * $2
  IntOp $4 $4 / 96
  IntOp $5 $5 / 96
  IntOp $6 $6 / 96
  IntOp $7 $7 / 96
  System::Call 'user32::CreateWindowEx(i r3, w "${__NSD_CheckBox_CLASS}", w "$(deleteAppData)", i ${__NSD_CheckBox_STYLE}, i r4, i r5, i r6, i r7, p r1, i0, i0, i0) i .s'
  Pop $DeleteAppDataCheckbox
  SendMessage $HWNDPARENT ${WM_GETFONT} 0 0 $1
  SendMessage $DeleteAppDataCheckbox ${WM_SETFONT} $1 1
FunctionEnd
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE un.ConfirmLeave
Function un.ConfirmLeave
  SendMessage $DeleteAppDataCheckbox ${BM_GETCHECK} 0 0 $DeleteAppDataCheckboxState
FunctionEnd
!define MUI_PAGE_CUSTOMFUNCTION_PRE un.SkipIfPassive
!insertmacro MUI_UNPAGE_CONFIRM

; 2. Uninstalling Page
!insertmacro MUI_UNPAGE_INSTFILES

;Languages
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_RESERVEFILE_LANGDLL
  !include "E:\AI_Agent\src-tauri\target\milestone03\release\nsis\x64\English.nsh"

Function .onInit
  ${GetOptions} $CMDLINE "/P" $PassiveMode
  ${IfNot} ${Errors}
    StrCpy $PassiveMode 1
  ${EndIf}

  ${GetOptions} $CMDLINE "/NS" $NoShortcutMode
  ${IfNot} ${Errors}
    StrCpy $NoShortcutMode 1
  ${EndIf}

  ${GetOptions} $CMDLINE "/UPDATE" $UpdateMode
  ${IfNot} ${Errors}
    StrCpy $UpdateMode 1
  ${EndIf}

  !if "${DISPLAYLANGUAGESELECTOR}" == "true"
    !insertmacro MUI_LANGDLL_DISPLAY
  !endif

  !insertmacro SetContext

  ${If} $INSTDIR == "${PLACEHOLDER_INSTALL_DIR}"
    ; Set default install location
    !if "${INSTALLMODE}" == "perMachine"
      ${If} ${RunningX64}
        !if "${ARCH}" == "x64"
          StrCpy $INSTDIR "$PROGRAMFILES64\${PRODUCTNAME}"
        !else if "${ARCH}" == "arm64"
          StrCpy $INSTDIR "$PROGRAMFILES64\${PRODUCTNAME}"
        !else
          StrCpy $INSTDIR "$PROGRAMFILES\${PRODUCTNAME}"
        !endif
      ${Else}
        StrCpy $INSTDIR "$PROGRAMFILES\${PRODUCTNAME}"
      ${EndIf}
    !else if "${INSTALLMODE}" == "currentUser"
      StrCpy $INSTDIR "$LOCALAPPDATA\Programs\${PRODUCTNAME}"
    !endif

    Call RestorePreviousInstallLocation
  ${EndIf}


  !if "${INSTALLMODE}" == "both"
    !insertmacro MULTIUSER_INIT
  !endif

  ; Abort downgrades if they are disabled, in the modes that skip the reinstall page choice:
  ; silent, passive and update
  !if "${ALLOWDOWNGRADES}" == "false"
  ${If} ${Silent}
  ${OrIf} $PassiveMode = 1
  ${OrIf} $UpdateMode = 1
    ReadRegStr $R0 SHCTX "${UNINSTKEY}" "DisplayVersion"
    nsis_tauri_utils::SemverCompare "${VERSION}" $R0
    Pop $R0
    ; If downgrading
    ${If} $R0 = -1
      ${If} ${Silent}
        System::Call 'kernel32::AttachConsole(i -1)i.r0'
        ${If} $0 <> 0
          System::Call 'kernel32::GetStdHandle(i -11)i.r0'
          System::call 'kernel32::SetConsoleTextAttribute(i r0, i 0x0004)' ; set red color
          FileWrite $0 "$(silentDowngrades)"
        ${EndIf}
      ${Else}
        MessageBox MB_ICONSTOP "$(silentDowngrades)"
      ${EndIf}
      Abort
    ${EndIf}
  ${EndIf}
  !endif
FunctionEnd

Section WebView2
  ; Check if Webview2 is already installed and skip this section
  ${If} ${RunningX64}
    ReadRegStr $4 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\${WEBVIEW2APPGUID}" "pv"
  ${Else}
    ReadRegStr $4 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\${WEBVIEW2APPGUID}" "pv"
  ${EndIf}
  ${If} $4 == ""
    ReadRegStr $4 HKCU "SOFTWARE\Microsoft\EdgeUpdate\Clients\${WEBVIEW2APPGUID}" "pv"
  ${EndIf}

  ${If} $4 == ""
    ; Webview2 installation
    ;
    ; Skip if updating
    ${If} $UpdateMode <> 1
      !if "${INSTALLWEBVIEW2MODE}" == "downloadBootstrapper"
        Delete "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        DetailPrint "$(webview2Downloading)"
        NSISdl::download "https://go.microsoft.com/fwlink/p/?LinkId=2124703" "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        Pop $0
        ${If} $0 == "success"
          DetailPrint "$(webview2DownloadSuccess)"
        ${Else}
          DetailPrint "$(webview2DownloadError)"
          Abort "$(webview2AbortError)"
        ${EndIf}
        StrCpy $6 "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        Goto install_webview2
      !endif

      !if "${INSTALLWEBVIEW2MODE}" == "embedBootstrapper"
        Delete "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        File "/oname=$TEMP\MicrosoftEdgeWebview2Setup.exe" "${WEBVIEW2BOOTSTRAPPERPATH}"
        DetailPrint "$(installingWebview2)"
        StrCpy $6 "$TEMP\MicrosoftEdgeWebview2Setup.exe"
        Goto install_webview2
      !endif

      !if "${INSTALLWEBVIEW2MODE}" == "offlineInstaller"
        Delete "$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe"
        File "/oname=$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe" "${WEBVIEW2INSTALLERPATH}"
        DetailPrint "$(installingWebview2)"
        StrCpy $6 "$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe"
        Goto install_webview2
      !endif

      Goto webview2_done

      install_webview2:
        DetailPrint "$(installingWebview2)"
        ; $6 holds the path to the webview2 installer
        ExecWait "$6 ${WEBVIEW2INSTALLERARGS} /install" $1
        ${If} $1 = 0
          DetailPrint "$(webview2InstallSuccess)"
        ${Else}
          DetailPrint "$(webview2InstallError)"
          Abort "$(webview2AbortError)"
        ${EndIf}
      webview2_done:
    ${EndIf}
  ${Else}
    !if "${MINIMUMWEBVIEW2VERSION}" != ""
      ${VersionCompare} "${MINIMUMWEBVIEW2VERSION}" "$4" $R0
      ${If} $R0 = 1
        update_webview:
          DetailPrint "$(installingWebview2)"
          ${If} ${RunningX64}
            ReadRegStr $R1 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate" "path"
          ${Else}
            ReadRegStr $R1 HKLM "SOFTWARE\Microsoft\EdgeUpdate" "path"
          ${EndIf}
          ${If} $R1 == ""
            ReadRegStr $R1 HKCU "SOFTWARE\Microsoft\EdgeUpdate" "path"
          ${EndIf}
          ${If} $R1 != ""
            ; Chromium updater docs: https://source.chromium.org/chromium/chromium/src/+/main:docs/updater/user_manual.md
            ; Modified from "HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Microsoft EdgeWebView\ModifyPath"
            ExecWait `"$R1" /install appguid=${WEBVIEW2APPGUID}&needsadmin=true` $1
            ${If} $1 = 0
              DetailPrint "$(webview2InstallSuccess)"
            ${Else}
              MessageBox MB_ICONEXCLAMATION|MB_ABORTRETRYIGNORE "$(webview2InstallError)" IDIGNORE ignore IDRETRY update_webview
              Quit
              ignore:
            ${EndIf}
          ${EndIf}
      ${EndIf}
    !endif
  ${EndIf}
SectionEnd

Section Install
  SetOutPath $INSTDIR

  !ifmacrodef NSIS_HOOK_PREINSTALL
    !insertmacro NSIS_HOOK_PREINSTALL
  !endif

  !insertmacro CheckIfAppIsRunning "$INSTDIR\${MAINBINARYNAME}.exe" "${PRODUCTNAME}"

  ; Copy main executable
  File "${MAINBINARYSRCPATH}"

  ; Copy resources
    CreateDirectory "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\licenses"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\splitmix64"
    CreateDirectory "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info\licenses"
    CreateDirectory "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\fft\pocketfft"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy.libs"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\multiarray"
    CreateDirectory "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg\_dsolve"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\stats\_levy_stable"
    CreateDirectory "$INSTDIR\resources\backend\_internal"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\optimize\_highspy"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\spatial\transform"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\include\numpy\libdivide"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\special"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\_lib\_uarray"
    CreateDirectory "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info"
    CreateDirectory "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\mt19937"
    CreateDirectory "$INSTDIR\resources\backend\_internal\rasterio"
    CreateDirectory "$INSTDIR\resources\backend\_internal\pydantic_core"
    CreateDirectory "$INSTDIR\resources\backend\_internal\websockets"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy"
    CreateDirectory "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info"
    CreateDirectory "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\linalg"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\stats\_rcont"
    CreateDirectory "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy\random"
    CreateDirectory "$INSTDIR\resources\backend\_internal\rasterio\proj_data"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\ma"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\optimize\_lsq"
    CreateDirectory "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info\licenses"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\spatial"
    CreateDirectory "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\licenses"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy\_core"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\sfc64"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\ndimage"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\optimize"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\highway"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\umath\svml"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\common\pythoncapi-compat"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\linalg\lapack_lite"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg\_eigen\arpack"
    CreateDirectory "$INSTDIR\resources\backend\_internal\setuptools\_vendor\jaraco\text"
    CreateDirectory "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\licenses"
    CreateDirectory "$INSTDIR\resources\backend\_internal\certifi"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy.libs"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\interpolate"
    CreateDirectory "$INSTDIR\resources\backend"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\philox"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\pcg64"
    CreateDirectory "$INSTDIR\resources\backend\_internal\rasterio.libs"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy\fft"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\npysort\x86-simd-sort"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\sparse"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\integrate"
    CreateDirectory "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\licenses"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\_lib"
    CreateDirectory "$INSTDIR\resources\backend\_internal\PIL"
    CreateDirectory "$INSTDIR\resources\backend\_internal\rasterio\gdal_data"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\optimize\_trlib"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy\linalg"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\fft\_duccfft"
    CreateDirectory "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\distributions"
    CreateDirectory "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info\licenses"
    CreateDirectory "$INSTDIR\resources\backend\_internal\scipy\stats"
    File /a "/oname=resources\backend\_internal\PIL\_avif.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\PIL\_avif.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\PIL\_imaging.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\PIL\_imaging.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\PIL\_imagingcms.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\PIL\_imagingcms.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\PIL\_imagingft.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\PIL\_imagingft.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\PIL\_imagingtk.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\PIL\_imagingtk.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\PIL\_webp.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\PIL\_webp.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\VCRUNTIME140.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\VCRUNTIME140.dll"
    File /a "/oname=resources\backend\_internal\VCRUNTIME140_1.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\VCRUNTIME140_1.dll"
    File /a "/oname=resources\backend\_internal\_asyncio.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_asyncio.pyd"
    File /a "/oname=resources\backend\_internal\_bz2.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_bz2.pyd"
    File /a "/oname=resources\backend\_internal\_ctypes.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_ctypes.pyd"
    File /a "/oname=resources\backend\_internal\_decimal.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_decimal.pyd"
    File /a "/oname=resources\backend\_internal\_elementtree.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_elementtree.pyd"
    File /a "/oname=resources\backend\_internal\_hashlib.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_hashlib.pyd"
    File /a "/oname=resources\backend\_internal\_lzma.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_lzma.pyd"
    File /a "/oname=resources\backend\_internal\_multiprocessing.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_multiprocessing.pyd"
    File /a "/oname=resources\backend\_internal\_overlapped.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_overlapped.pyd"
    File /a "/oname=resources\backend\_internal\_queue.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_queue.pyd"
    File /a "/oname=resources\backend\_internal\_socket.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_socket.pyd"
    File /a "/oname=resources\backend\_internal\_sqlite3.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_sqlite3.pyd"
    File /a "/oname=resources\backend\_internal\_ssl.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_ssl.pyd"
    File /a "/oname=resources\backend\_internal\_uuid.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_uuid.pyd"
    File /a "/oname=resources\backend\_internal\_wmi.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_wmi.pyd"
    File /a "/oname=resources\backend\_internal\_zoneinfo.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\_zoneinfo.pyd"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-console-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-console-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-datetime-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-datetime-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-debug-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-debug-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-errorhandling-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-errorhandling-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-fibers-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-fibers-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-fibers-l1-1-1.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-fibers-l1-1-1.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-file-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-file-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-file-l1-2-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-file-l1-2-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-file-l2-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-file-l2-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-handle-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-handle-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-heap-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-heap-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-interlocked-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-interlocked-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-kernel32-legacy-l1-1-1.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-kernel32-legacy-l1-1-1.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-libraryloader-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-libraryloader-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-localization-l1-2-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-localization-l1-2-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-memory-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-memory-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-namedpipe-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-namedpipe-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-processenvironment-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-processenvironment-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-processthreads-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-processthreads-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-processthreads-l1-1-1.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-processthreads-l1-1-1.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-profile-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-profile-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-rtlsupport-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-rtlsupport-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-string-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-string-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-synch-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-synch-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-synch-l1-2-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-synch-l1-2-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-sysinfo-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-sysinfo-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-sysinfo-l1-2-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-sysinfo-l1-2-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-timezone-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-timezone-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-core-util-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-core-util-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-conio-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-conio-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-convert-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-convert-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-environment-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-environment-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-filesystem-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-filesystem-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-heap-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-heap-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-locale-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-locale-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-math-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-math-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-private-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-private-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-process-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-process-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-runtime-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-runtime-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-stdio-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-stdio-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-string-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-string-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-time-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-time-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\api-ms-win-crt-utility-l1-1-0.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\api-ms-win-crt-utility-l1-1-0.dll"
    File /a "/oname=resources\backend\_internal\attrs-26.1.0.dist-info\INSTALLER" "E:\AI_Agent\src-tauri\resources\backend\_internal\attrs-26.1.0.dist-info\INSTALLER"
    File /a "/oname=resources\backend\_internal\attrs-26.1.0.dist-info\METADATA" "E:\AI_Agent\src-tauri\resources\backend\_internal\attrs-26.1.0.dist-info\METADATA"
    File /a "/oname=resources\backend\_internal\attrs-26.1.0.dist-info\RECORD" "E:\AI_Agent\src-tauri\resources\backend\_internal\attrs-26.1.0.dist-info\RECORD"
    File /a "/oname=resources\backend\_internal\attrs-26.1.0.dist-info\REQUESTED" "E:\AI_Agent\src-tauri\resources\backend\_internal\attrs-26.1.0.dist-info\REQUESTED"
    File /a "/oname=resources\backend\_internal\attrs-26.1.0.dist-info\WHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\attrs-26.1.0.dist-info\WHEEL"
    File /a "/oname=resources\backend\_internal\attrs-26.1.0.dist-info\licenses\LICENSE" "E:\AI_Agent\src-tauri\resources\backend\_internal\attrs-26.1.0.dist-info\licenses\LICENSE"
    File /a "/oname=resources\backend\_internal\base_library.zip" "E:\AI_Agent\src-tauri\resources\backend\_internal\base_library.zip"
    File /a "/oname=resources\backend\_internal\certifi\cacert.pem" "E:\AI_Agent\src-tauri\resources\backend\_internal\certifi\cacert.pem"
    File /a "/oname=resources\backend\_internal\certifi\py.typed" "E:\AI_Agent\src-tauri\resources\backend\_internal\certifi\py.typed"
    File /a "/oname=resources\backend\_internal\click-8.5.0.dist-info\INSTALLER" "E:\AI_Agent\src-tauri\resources\backend\_internal\click-8.5.0.dist-info\INSTALLER"
    File /a "/oname=resources\backend\_internal\click-8.5.0.dist-info\METADATA" "E:\AI_Agent\src-tauri\resources\backend\_internal\click-8.5.0.dist-info\METADATA"
    File /a "/oname=resources\backend\_internal\click-8.5.0.dist-info\RECORD" "E:\AI_Agent\src-tauri\resources\backend\_internal\click-8.5.0.dist-info\RECORD"
    File /a "/oname=resources\backend\_internal\click-8.5.0.dist-info\REQUESTED" "E:\AI_Agent\src-tauri\resources\backend\_internal\click-8.5.0.dist-info\REQUESTED"
    File /a "/oname=resources\backend\_internal\click-8.5.0.dist-info\WHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\click-8.5.0.dist-info\WHEEL"
    File /a "/oname=resources\backend\_internal\click-8.5.0.dist-info\licenses\LICENSE.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\click-8.5.0.dist-info\licenses\LICENSE.txt"
    File /a "/oname=resources\backend\_internal\libcrypto-3-x64.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\libcrypto-3-x64.dll"
    File /a "/oname=resources\backend\_internal\libffi-8.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\libffi-8.dll"
    File /a "/oname=resources\backend\_internal\libssl-3-x64.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\libssl-3-x64.dll"
    File /a "/oname=resources\backend\_internal\numpy\_core\_multiarray_tests.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\_core\_multiarray_tests.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\_core\_multiarray_umath.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\_core\_multiarray_umath.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\fft\_pocketfft_umath.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\fft\_pocketfft_umath.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\linalg\_umath_linalg.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\linalg\_umath_linalg.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\_bounded_integers.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\_bounded_integers.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\_common.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\_common.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\_generator.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\_generator.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\_mt19937.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\_mt19937.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\_pcg64.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\_pcg64.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\_philox.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\_philox.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\_sfc64.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\_sfc64.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\bit_generator.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\bit_generator.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy\random\mtrand.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy\random\mtrand.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\DELVEWHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\DELVEWHEEL"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\INSTALLER" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\INSTALLER"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\METADATA" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\METADATA"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\RECORD" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\RECORD"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\REQUESTED" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\REQUESTED"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\WHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\WHEEL"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\entry_points.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\entry_points.txt"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\LICENSE.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\LICENSE.txt"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\include\numpy\libdivide\LICENSE.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\include\numpy\libdivide\LICENSE.txt"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\common\pythoncapi-compat\COPYING" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\common\pythoncapi-compat\COPYING"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\highway\LICENSE" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\highway\LICENSE"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\multiarray\dragon4_LICENSE.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\multiarray\dragon4_LICENSE.txt"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\npysort\x86-simd-sort\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\npysort\x86-simd-sort\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\umath\svml\LICENSE" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\umath\svml\LICENSE"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\fft\pocketfft\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\fft\pocketfft\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\linalg\lapack_lite\LICENSE.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\linalg\lapack_lite\LICENSE.txt"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\ma\LICENSE" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\ma\LICENSE"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\distributions\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\distributions\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\mt19937\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\mt19937\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\pcg64\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\pcg64\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\philox\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\philox\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\sfc64\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\sfc64\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\splitmix64\LICENSE.md" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\splitmix64\LICENSE.md"
    File /a "/oname=resources\backend\_internal\numpy.libs\libscipy_openblas64_-ed4f167a5330424524f45258e7ca2c8d.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy.libs\libscipy_openblas64_-ed4f167a5330424524f45258e7ca2c8d.dll"
    File /a "/oname=resources\backend\_internal\numpy.libs\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\numpy.libs\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll"
    File /a "/oname=resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\INSTALLER" "E:\AI_Agent\src-tauri\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\INSTALLER"
    File /a "/oname=resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\METADATA" "E:\AI_Agent\src-tauri\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\METADATA"
    File /a "/oname=resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\RECORD" "E:\AI_Agent\src-tauri\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\RECORD"
    File /a "/oname=resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\REQUESTED" "E:\AI_Agent\src-tauri\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\REQUESTED"
    File /a "/oname=resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\WHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\WHEEL"
    File /a "/oname=resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\entry_points.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\entry_points.txt"
    File /a "/oname=resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\licenses\LICENSE" "E:\AI_Agent\src-tauri\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\licenses\LICENSE"
    File /a "/oname=resources\backend\_internal\pluggy-1.7.0.dist-info\INSTALLER" "E:\AI_Agent\src-tauri\resources\backend\_internal\pluggy-1.7.0.dist-info\INSTALLER"
    File /a "/oname=resources\backend\_internal\pluggy-1.7.0.dist-info\METADATA" "E:\AI_Agent\src-tauri\resources\backend\_internal\pluggy-1.7.0.dist-info\METADATA"
    File /a "/oname=resources\backend\_internal\pluggy-1.7.0.dist-info\RECORD" "E:\AI_Agent\src-tauri\resources\backend\_internal\pluggy-1.7.0.dist-info\RECORD"
    File /a "/oname=resources\backend\_internal\pluggy-1.7.0.dist-info\REQUESTED" "E:\AI_Agent\src-tauri\resources\backend\_internal\pluggy-1.7.0.dist-info\REQUESTED"
    File /a "/oname=resources\backend\_internal\pluggy-1.7.0.dist-info\WHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\pluggy-1.7.0.dist-info\WHEEL"
    File /a "/oname=resources\backend\_internal\pluggy-1.7.0.dist-info\licenses\LICENSE" "E:\AI_Agent\src-tauri\resources\backend\_internal\pluggy-1.7.0.dist-info\licenses\LICENSE"
    File /a "/oname=resources\backend\_internal\pluggy-1.7.0.dist-info\top_level.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\pluggy-1.7.0.dist-info\top_level.txt"
    File /a "/oname=resources\backend\_internal\pydantic-2.14.1.dist-info\INSTALLER" "E:\AI_Agent\src-tauri\resources\backend\_internal\pydantic-2.14.1.dist-info\INSTALLER"
    File /a "/oname=resources\backend\_internal\pydantic-2.14.1.dist-info\METADATA" "E:\AI_Agent\src-tauri\resources\backend\_internal\pydantic-2.14.1.dist-info\METADATA"
    File /a "/oname=resources\backend\_internal\pydantic-2.14.1.dist-info\RECORD" "E:\AI_Agent\src-tauri\resources\backend\_internal\pydantic-2.14.1.dist-info\RECORD"
    File /a "/oname=resources\backend\_internal\pydantic-2.14.1.dist-info\REQUESTED" "E:\AI_Agent\src-tauri\resources\backend\_internal\pydantic-2.14.1.dist-info\REQUESTED"
    File /a "/oname=resources\backend\_internal\pydantic-2.14.1.dist-info\WHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\pydantic-2.14.1.dist-info\WHEEL"
    File /a "/oname=resources\backend\_internal\pydantic-2.14.1.dist-info\licenses\LICENSE" "E:\AI_Agent\src-tauri\resources\backend\_internal\pydantic-2.14.1.dist-info\licenses\LICENSE"
    File /a "/oname=resources\backend\_internal\pydantic_core\_pydantic_core.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\pydantic_core\_pydantic_core.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\pyexpat.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\pyexpat.pyd"
    File /a "/oname=resources\backend\_internal\python312.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\python312.dll"
    File /a "/oname=resources\backend\_internal\rasterio\_base.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_base.c"
    File /a "/oname=resources\backend\_internal\rasterio\_base.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_base.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_base.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_base.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_base.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_base.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_env.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_env.c"
    File /a "/oname=resources\backend\_internal\rasterio\_env.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_env.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_env.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_env.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_env.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_env.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_err.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_err.c"
    File /a "/oname=resources\backend\_internal\rasterio\_err.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_err.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_err.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_err.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_err.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_err.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_example.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_example.c"
    File /a "/oname=resources\backend\_internal\rasterio\_example.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_example.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_example.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_example.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_features.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_features.c"
    File /a "/oname=resources\backend\_internal\rasterio\_features.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_features.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_features.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_features.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_features.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_features.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_filepath.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_filepath.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_filepath.cpp" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_filepath.cpp"
    File /a "/oname=resources\backend\_internal\rasterio\_filepath.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_filepath.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_filepath.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_filepath.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_fill.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_fill.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_fill.cpp" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_fill.cpp"
    File /a "/oname=resources\backend\_internal\rasterio\_fill.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_fill.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_io.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_io.c"
    File /a "/oname=resources\backend\_internal\rasterio\_io.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_io.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_io.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_io.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_io.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_io.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_transform.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_transform.c"
    File /a "/oname=resources\backend\_internal\rasterio\_transform.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_transform.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_transform.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_transform.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_version.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_version.c"
    File /a "/oname=resources\backend\_internal\rasterio\_version.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_version.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_version.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_version.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_version.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_version.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_vsiopener.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_vsiopener.c"
    File /a "/oname=resources\backend\_internal\rasterio\_vsiopener.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_vsiopener.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_vsiopener.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_vsiopener.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_vsiopener.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_vsiopener.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\_warp.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_warp.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\_warp.cpp" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_warp.cpp"
    File /a "/oname=resources\backend\_internal\rasterio\_warp.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_warp.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\_warp.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\_warp.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\cache.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\cache.c"
    File /a "/oname=resources\backend\_internal\rasterio\cache.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\cache.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\cache.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\cache.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\crs.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\crs.c"
    File /a "/oname=resources\backend\_internal\rasterio\crs.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\crs.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\crs.pxd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\crs.pxd"
    File /a "/oname=resources\backend\_internal\rasterio\crs.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\crs.pyx"
    File /a "/oname=resources\backend\_internal\rasterio\gdal.pxi" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal.pxi"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\GDAL-targets-debug.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\GDAL-targets-debug.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\GDAL-targets-release.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\GDAL-targets-release.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\GDAL-targets.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\GDAL-targets.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\GDALConfig.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\GDALConfig.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\GDALConfigVersion.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\GDALConfigVersion.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\GDALLogoBW.svg" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\GDALLogoBW.svg"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\GDALLogoColor.svg" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\GDALLogoColor.svg"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\GDALLogoGS.svg" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\GDALLogoGS.svg"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\LICENSE.TXT" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\LICENSE.TXT"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\MM_m_idofic.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\MM_m_idofic.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\bag_template.xml" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\bag_template.xml"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\copyright" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\copyright"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\cubewerx_extra.wkt" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\cubewerx_extra.wkt"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\default.rsc" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\default.rsc"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ecw_cs.wkt" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ecw_cs.wkt"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\eedaconf.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\eedaconf.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\epsg.wkt" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\epsg.wkt"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\esri_StatePlane_extra.wkt" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\esri_StatePlane_extra.wkt"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gdal_algorithm.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gdal_algorithm.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gdalg.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gdalg.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gdalicon.png" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gdalicon.png"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gdalinfo_output.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gdalinfo_output.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gdalmdiminfo_output.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gdalmdiminfo_output.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gdaltileindex.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gdaltileindex.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gdalvrt.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gdalvrt.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gfs.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gfs.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gml_registry.xml" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gml_registry.xml"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gml_registry.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gml_registry.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_center.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_center.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_process.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_process.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_subcenter.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_subcenter.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_0.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_0.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_1.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_1.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_13.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_13.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_14.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_14.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_15.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_15.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_16.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_16.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_17.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_17.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_18.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_18.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_19.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_19.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_190.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_190.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_191.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_191.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_2.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_2.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_20.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_20.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_21.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_21.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_22.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_22.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_3.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_3.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_4.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_4.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_5.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_5.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_6.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_6.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_7.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_7.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_0.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_0.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_1.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_1.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_191.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_191.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_2.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_2.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_3.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_3.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_4.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_4.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_0.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_0.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_1.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_1.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_2.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_2.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_0.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_0.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_1.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_1.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_2.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_2.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_3.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_3.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_0.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_0.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_3.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_3.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_4.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_4.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_5.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_5.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_6.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_6.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_7.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_7.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_0.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_0.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_1.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_1.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_2.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_2.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_3.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_3.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_4.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_4.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_5.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_5.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_6.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_6.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_0.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_0.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_1.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_1.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_10.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_10.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_2.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_2.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_3.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_3.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_4.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_4.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_5.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_5.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_6.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_6.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_7.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_7.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_8.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_8.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_9.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_9.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_Canada.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_Canada.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_HPC.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_HPC.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_MRMS.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_MRMS.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_NCEP.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_NCEP.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_NDFD.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_NDFD.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_index.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_index.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_4_5.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_5.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\grib2_table_versions.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\grib2_table_versions.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gt_datum.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gt_datum.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\gt_ellips.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\gt_ellips.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\header.dxf" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\header.dxf"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\inspire_cp_BasicPropertyUnit.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\inspire_cp_BasicPropertyUnit.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralBoundary.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralBoundary.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralParcel.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralParcel.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralZoning.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralZoning.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmArea.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmArea.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmBdry.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmBdry.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmPt.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmPt.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_BldA.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_BldA.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_BldL.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_BldL.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_Cntr.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_Cntr.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_CommBdry.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_CommBdry.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_CommPt.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_CommPt.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_Cstline.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_Cstline.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_ElevPt.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_ElevPt.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_GCP.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_GCP.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_LeveeEdge.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_LeveeEdge.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RailCL.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RailCL.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdASL.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdASL.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdArea.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdArea.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdCompt.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdCompt.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdEdg.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdEdg.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdMgtBdry.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdMgtBdry.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdSgmtA.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdSgmtA.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RvrMgtBdry.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RvrMgtBdry.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBAPt.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBAPt.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBArea.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBArea.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBBdry.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBBdry.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WA.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WA.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WL.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WL.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WStrA.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WStrA.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WStrL.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WStrL.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\leaflet_template.html" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\leaflet_template.html"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\netcdf_config.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\netcdf_config.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\nitf_spec.xml" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\nitf_spec.xml"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\nitf_spec.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\nitf_spec.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ogr_fields_override.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ogr_fields_override.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ogrinfo_output.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ogrinfo_output.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ogrvrt.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ogrvrt.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\osmconf.ini" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\osmconf.ini"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ozi_datum.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ozi_datum.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ozi_ellips.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ozi_ellips.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\pci_datum.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\pci_datum.txt"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\pci_ellips.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\pci_ellips.txt"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\pdfcomposition.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\pdfcomposition.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\pds4_template.xml" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\pds4_template.xml"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\plscenesconf.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\plscenesconf.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ruian_vf_ob_v1.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ruian_vf_ob_v1.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ruian_vf_st_uvoh_v1.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ruian_vf_st_uvoh_v1.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ruian_vf_st_v1.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ruian_vf_st_v1.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\ruian_vf_v1.gfs" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\ruian_vf_v1.gfs"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\s57agencies.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\s57agencies.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\s57attributes.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\s57attributes.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\s57expectedinput.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\s57expectedinput.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\s57objectclasses.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\s57objectclasses.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\seed_2d.dgn" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\seed_2d.dgn"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\seed_3d.dgn" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\seed_3d.dgn"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\stateplane.csv" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\stateplane.csv"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\template_tiles.mapml" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\template_tiles.mapml"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\tms_LINZAntarticaMapTileGrid.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\tms_LINZAntarticaMapTileGrid.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\tms_MapML_APSTILE.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\tms_MapML_APSTILE.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\tms_MapML_CBMTILE.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\tms_MapML_CBMTILE.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\tms_NZTM2000.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\tms_NZTM2000.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\trailer.dxf" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\trailer.dxf"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\usage" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\usage"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\vcpkg-cmake-wrapper.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\vcpkg-cmake-wrapper.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\vcpkg-spdx-resources.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\vcpkg-spdx-resources.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\vcpkg.spdx.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\vcpkg.spdx.json"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\vcpkg_abi_info.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\vcpkg_abi_info.txt"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\vdv452.xml" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\vdv452.xml"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\vdv452.xsd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\vdv452.xsd"
    File /a "/oname=resources\backend\_internal\rasterio\gdal_data\vicar.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\gdal_data\vicar.json"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\CH" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\CH"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\GL27" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\GL27"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\ITRF2000" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\ITRF2000"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\ITRF2008" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\ITRF2008"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\ITRF2014" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\ITRF2014"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\ITRF2020" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\ITRF2020"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\copyright" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\copyright"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\deformation_model.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\deformation_model.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\nad.lst" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\nad.lst"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\nad27" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\nad27"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\nad83" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\nad83"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\other.extra" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\other.extra"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj-config-version.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj-config-version.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj-config.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj-config.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj-targets-debug.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj-targets-debug.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj-targets-release.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj-targets-release.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj-targets.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj-targets.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj.db" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj.db"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj.ini" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj.ini"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj4-targets-debug.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj4-targets-debug.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj4-targets-release.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj4-targets-release.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\proj4-targets.cmake" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\proj4-targets.cmake"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\projjson.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\projjson.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\triangulation.schema.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\triangulation.schema.json"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\usage" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\usage"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\vcpkg-spdx-resources.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\vcpkg-spdx-resources.json"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\vcpkg.spdx.json" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\vcpkg.spdx.json"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\vcpkg_abi_info.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\vcpkg_abi_info.txt"
    File /a "/oname=resources\backend\_internal\rasterio\proj_data\world" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\proj_data\world"
    File /a "/oname=resources\backend\_internal\rasterio\shutil.c" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\shutil.c"
    File /a "/oname=resources\backend\_internal\rasterio\shutil.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\shutil.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\rasterio\shutil.pyx" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio\shutil.pyx"
    File /a "/oname=resources\backend\_internal\rasterio.libs\Lerc-bd596e02be0e2a4d97970986d405b306.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\Lerc-bd596e02be0e2a4d97970986d405b306.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\freexl-1-f984fed45cb40bcf96e583a5d17e3e9f.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\freexl-1-f984fed45cb40bcf96e583a5d17e3e9f.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\gdal-ca23e679e52f19649323f953f4a92966.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\gdal-ca23e679e52f19649323f953f4a92966.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\geos-353ca83806e765757ee1ac85230fad94.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\geos-353ca83806e765757ee1ac85230fad94.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\geos_c-ee1211e77d58bd95402e455720af8ce9.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\geos_c-ee1211e77d58bd95402e455720af8ce9.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\geotiff-5e33421f0ae45bc20fe26c869841819c.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\geotiff-5e33421f0ae45bc20fe26c869841819c.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\gif-1107c2c29ae9bc2dab88f8650eedf346.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\gif-1107c2c29ae9bc2dab88f8650eedf346.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\hdf5-90d65e8c6734fd05e7f71019aea56e63.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\hdf5-90d65e8c6734fd05e7f71019aea56e63.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\hdf5_hl-0f04f4391d2304f0c3baecb4b64cc3c7.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\hdf5_hl-0f04f4391d2304f0c3baecb4b64cc3c7.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\iconv-2-ebb8d125e8964d978f001ad727bb1f6a.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\iconv-2-ebb8d125e8964d978f001ad727bb1f6a.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\jpeg62-f01e7c07b88707d3293da417a2270e8d.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\jpeg62-f01e7c07b88707d3293da417a2270e8d.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\json-c-69add94c2356636200f46910429b496e.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\json-c-69add94c2356636200f46910429b496e.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libcrypto-3-x64-2afd3870ac1ca9227daaf71022d519dd.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libcrypto-3-x64-2afd3870ac1ca9227daaf71022d519dd.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libcurl-59fd99b636208c0efd91cad8b4cf028c.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libcurl-59fd99b636208c0efd91cad8b4cf028c.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libexpat-533441caabb6e8e810f3c428aac8662a.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libexpat-533441caabb6e8e810f3c428aac8662a.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\liblzma-493fcad0ab8b3babd9c41dbd94a1afe5.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\liblzma-493fcad0ab8b3babd9c41dbd94a1afe5.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libpng16-644a70bf72a6c164e16c88d6a0c64f5b.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libpng16-644a70bf72a6c164e16c88d6a0c64f5b.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libpq-95c240938b5ffe9f0191160d951f9302.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libpq-95c240938b5ffe9f0191160d951f9302.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libsharpyuv-39f8caaabd4dd845629ed7064c22149b.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libsharpyuv-39f8caaabd4dd845629ed7064c22149b.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libssl-3-x64-cdfaf2036db9847e1470a7adabf3576a.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libssl-3-x64-cdfaf2036db9847e1470a7adabf3576a.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libwebp-c62a0ecd823a4ac55d020b1e5b4e214d.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libwebp-c62a0ecd823a4ac55d020b1e5b4e214d.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\libxml2-ee3a45b6842891635a7194ed3bf4439b.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\libxml2-ee3a45b6842891635a7194ed3bf4439b.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\minizip-a17a1f1144c99133fb8ac04c5fc0d727.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\minizip-a17a1f1144c99133fb8ac04c5fc0d727.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\netcdf-80fff5a18c54bb9f3a649624658cc0ae.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\netcdf-80fff5a18c54bb9f3a649624658cc0ae.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\openjp2-c1951c6e297b4dfbc1ecfed46df803af.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\openjp2-c1951c6e297b4dfbc1ecfed46df803af.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\pcre2-8-4250f3875b7c8017370f480e5933b922.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\pcre2-8-4250f3875b7c8017370f480e5933b922.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\proj_9-d142a65602e419d49589809f8c96ed95.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\proj_9-d142a65602e419d49589809f8c96ed95.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\qhull_r-9dfe5950fe3ffbeff1f83f37ef8a3b6a.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\qhull_r-9dfe5950fe3ffbeff1f83f37ef8a3b6a.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\spatialite-462100c3ae387a5046878044decbecb9.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\spatialite-462100c3ae387a5046878044decbecb9.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\sqlite3-a95e23ad82678982e28e9780f07ae1f7.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\sqlite3-a95e23ad82678982e28e9780f07ae1f7.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\szip-237b7e7db63858546dc0b6d1d1113e6c.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\szip-237b7e7db63858546dc0b6d1d1113e6c.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\tiff-ab336932b464eb213b8c0ba892721190.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\tiff-ab336932b464eb213b8c0ba892721190.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\tinyxml2-b1394948d9bf11d7822da2aabdf5ab40.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\tinyxml2-b1394948d9bf11d7822da2aabdf5ab40.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\zlib1-63e59a7591925180e9af63ff1cf293fb.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\zlib1-63e59a7591925180e9af63ff1cf293fb.dll"
    File /a "/oname=resources\backend\_internal\rasterio.libs\zstd-2363c320dd62f9f202293b4b1406aac1.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\rasterio.libs\zstd-2363c320dd62f9f202293b4b1406aac1.dll"
    File /a "/oname=resources\backend\_internal\scipy\_cyutility.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\_cyutility.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\_lib\_ccallback_c.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\_lib\_ccallback_c.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\_lib\_fpumode.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\_lib\_fpumode.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\_lib\_uarray\_uarray.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\_lib\_uarray\_uarray.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\_lib\messagestream.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\_lib\messagestream.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\fft\_duccfft\pyduccfft.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\fft\_duccfft\pyduccfft.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\integrate\_dop.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\integrate\_dop.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\integrate\_odepack.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\integrate\_odepack.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\integrate\_quadpack.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\integrate\_quadpack.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\integrate\_vode.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\integrate\_vode.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\interpolate\_dierckx.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\interpolate\_dierckx.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\interpolate\_fitpack.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\interpolate\_fitpack.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\interpolate\_interpnd.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\interpolate\_interpnd.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\interpolate\_ppoly.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\interpolate\_ppoly.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\interpolate\_rbfinterp_pythran.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\interpolate\_rbfinterp_pythran.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\interpolate\_rgi_cython.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\interpolate\_rgi_cython.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_batched_linalg.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_batched_linalg.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_cythonized_array_utils.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_cythonized_array_utils.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_decomp_interpolative.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_decomp_interpolative.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_decomp_update.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_decomp_update.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_fblas.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_fblas.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_flapack.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_flapack.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_internal_matfuncs.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_internal_matfuncs.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_linalg_pythran.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_linalg_pythran.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_matfuncs_sqrtm_triu.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_matfuncs_sqrtm_triu.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\_solve_toeplitz.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\_solve_toeplitz.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\cython_blas.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\cython_blas.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\linalg\cython_lapack.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\linalg\cython_lapack.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\ndimage\_nd_image.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\ndimage\_nd_image.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\ndimage\_ni_label.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\ndimage\_ni_label.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\ndimage\_rank_filter_1d.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\ndimage\_rank_filter_1d.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_bglu_dense.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_bglu_dense.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_direct.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_direct.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_group_columns.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_group_columns.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_highspy\_core.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_highspy\_core.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_highspy\_highs_options.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_highspy\_highs_options.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_lbfgsb.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_lbfgsb.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_lsap.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_lsap.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_lsq\givens_elimination.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_lsq\givens_elimination.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_minpack.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_minpack.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_moduleTNC.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_moduleTNC.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_pava_pybind.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_pava_pybind.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_slsqplib.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_slsqplib.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_trlib\_trlib.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_trlib\_trlib.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\optimize\_zeros.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\optimize\_zeros.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\_csparsetools.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\_csparsetools.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\_sparsetools.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\_sparsetools.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\csgraph\_flow.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\csgraph\_flow.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\csgraph\_matching.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\csgraph\_matching.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\csgraph\_min_spanning_tree.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\csgraph\_min_spanning_tree.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\csgraph\_reordering.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\csgraph\_reordering.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\csgraph\_shortest_path.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\csgraph\_shortest_path.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\csgraph\_tools.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\csgraph\_tools.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\csgraph\_traversal.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\csgraph\_traversal.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\linalg\_dsolve\_superlu.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\linalg\_dsolve\_superlu.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\linalg\_eigen\arpack\_arpacklib.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\linalg\_eigen\arpack\_arpacklib.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\sparse\linalg\_propack.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\sparse\linalg\_propack.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\spatial\_ckdtree.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\spatial\_ckdtree.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\spatial\_distance_pybind.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\spatial\_distance_pybind.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\spatial\_distance_wrap.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\spatial\_distance_wrap.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\spatial\_hausdorff.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\spatial\_hausdorff.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\spatial\_qhull.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\spatial\_qhull.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\spatial\_voronoi.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\spatial\_voronoi.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\spatial\transform\_rigid_transform_cy.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\spatial\transform\_rigid_transform_cy.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\spatial\transform\_rotation_cy.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\spatial\transform\_rotation_cy.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\special\_comb.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\special\_comb.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\special\_ellip_harm_2.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\special\_ellip_harm_2.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\special\_gufuncs.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\special\_gufuncs.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\special\_specfun.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\special\_specfun.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\special\_special_ufuncs.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\special\_special_ufuncs.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\special\_ufuncs.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\special\_ufuncs.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\special\_ufuncs_cxx.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\special\_ufuncs_cxx.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\special\cython_special.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\special\cython_special.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_ansari_swilk_statistics.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_ansari_swilk_statistics.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_biasedurn.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_biasedurn.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_levy_stable\levyst.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_levy_stable\levyst.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_qmc_cy.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_qmc_cy.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_qmvnt_cy.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_qmvnt_cy.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_rcont\rcont.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_rcont\rcont.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_sobol.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_sobol.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_stats.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_stats.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy\stats\_stats_pythran.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy\stats\_stats_pythran.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\scipy.libs\libscipy_openblas-197ee2fc9b4d071f7e048078cac74115.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\scipy.libs\libscipy_openblas-197ee2fc9b4d071f7e048078cac74115.dll"
    File /a "/oname=resources\backend\_internal\select.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\select.pyd"
    File /a "/oname=resources\backend\_internal\setuptools\_vendor\jaraco\text\Lorem ipsum.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\setuptools\_vendor\jaraco\text\Lorem ipsum.txt"
    File /a "/oname=resources\backend\_internal\sqlite3.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\sqlite3.dll"
    File /a "/oname=resources\backend\_internal\structlog-26.1.0.dist-info\INSTALLER" "E:\AI_Agent\src-tauri\resources\backend\_internal\structlog-26.1.0.dist-info\INSTALLER"
    File /a "/oname=resources\backend\_internal\structlog-26.1.0.dist-info\METADATA" "E:\AI_Agent\src-tauri\resources\backend\_internal\structlog-26.1.0.dist-info\METADATA"
    File /a "/oname=resources\backend\_internal\structlog-26.1.0.dist-info\RECORD" "E:\AI_Agent\src-tauri\resources\backend\_internal\structlog-26.1.0.dist-info\RECORD"
    File /a "/oname=resources\backend\_internal\structlog-26.1.0.dist-info\REQUESTED" "E:\AI_Agent\src-tauri\resources\backend\_internal\structlog-26.1.0.dist-info\REQUESTED"
    File /a "/oname=resources\backend\_internal\structlog-26.1.0.dist-info\WHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\structlog-26.1.0.dist-info\WHEEL"
    File /a "/oname=resources\backend\_internal\structlog-26.1.0.dist-info\licenses\LICENSE-APACHE" "E:\AI_Agent\src-tauri\resources\backend\_internal\structlog-26.1.0.dist-info\licenses\LICENSE-APACHE"
    File /a "/oname=resources\backend\_internal\structlog-26.1.0.dist-info\licenses\LICENSE-MIT" "E:\AI_Agent\src-tauri\resources\backend\_internal\structlog-26.1.0.dist-info\licenses\LICENSE-MIT"
    File /a "/oname=resources\backend\_internal\structlog-26.1.0.dist-info\licenses\NOTICE" "E:\AI_Agent\src-tauri\resources\backend\_internal\structlog-26.1.0.dist-info\licenses\NOTICE"
    File /a "/oname=resources\backend\_internal\ucrtbase.dll" "E:\AI_Agent\src-tauri\resources\backend\_internal\ucrtbase.dll"
    File /a "/oname=resources\backend\_internal\unicodedata.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\unicodedata.pyd"
    File /a "/oname=resources\backend\_internal\websockets\speedups.cp312-win_amd64.pyd" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets\speedups.cp312-win_amd64.pyd"
    File /a "/oname=resources\backend\_internal\websockets-17.2.dist-info\INSTALLER" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets-17.2.dist-info\INSTALLER"
    File /a "/oname=resources\backend\_internal\websockets-17.2.dist-info\METADATA" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets-17.2.dist-info\METADATA"
    File /a "/oname=resources\backend\_internal\websockets-17.2.dist-info\RECORD" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets-17.2.dist-info\RECORD"
    File /a "/oname=resources\backend\_internal\websockets-17.2.dist-info\REQUESTED" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets-17.2.dist-info\REQUESTED"
    File /a "/oname=resources\backend\_internal\websockets-17.2.dist-info\WHEEL" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets-17.2.dist-info\WHEEL"
    File /a "/oname=resources\backend\_internal\websockets-17.2.dist-info\entry_points.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets-17.2.dist-info\entry_points.txt"
    File /a "/oname=resources\backend\_internal\websockets-17.2.dist-info\licenses\LICENSE" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets-17.2.dist-info\licenses\LICENSE"
    File /a "/oname=resources\backend\_internal\websockets-17.2.dist-info\top_level.txt" "E:\AI_Agent\src-tauri\resources\backend\_internal\websockets-17.2.dist-info\top_level.txt"
    File /a "/oname=resources\backend\app.exe" "E:\AI_Agent\src-tauri\resources\backend\app.exe"

  ; Copy external binaries

  ; Create file associations

  ; Register deep links

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Save $INSTDIR in registry for future installations
  WriteRegStr SHCTX "${MANUPRODUCTKEY}" "" $INSTDIR

  !if "${INSTALLMODE}" == "both"
    ; Save install mode to be selected by default for the next installation such as updating
    ; or when uninstalling
    WriteRegStr SHCTX "${UNINSTKEY}" $MultiUser.InstallMode 1
  !endif

  ; Remove old main binary if it doesn't match new main binary name
  ReadRegStr $OldMainBinaryName SHCTX "${UNINSTKEY}" "MainBinaryName"
  ${If} $OldMainBinaryName != ""
  ${AndIf} $OldMainBinaryName != "${MAINBINARYNAME}.exe"
    Delete "$INSTDIR\$OldMainBinaryName"
  ${EndIf}

  ; Save current MAINBINARYNAME for future updates
  WriteRegStr SHCTX "${UNINSTKEY}" "MainBinaryName" "${MAINBINARYNAME}.exe"

  ; Registry information for add/remove programs
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayName" "${PRODUCTNAME}"
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayIcon" "$\"$INSTDIR\${MAINBINARYNAME}.exe$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr SHCTX "${UNINSTKEY}" "Publisher" "${MANUFACTURER}"
  WriteRegStr SHCTX "${UNINSTKEY}" "InstallLocation" "$\"$INSTDIR$\""
  WriteRegStr SHCTX "${UNINSTKEY}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegDWORD SHCTX "${UNINSTKEY}" "NoModify" "1"
  WriteRegDWORD SHCTX "${UNINSTKEY}" "NoRepair" "1"

  ${GetSize} "$INSTDIR" "/M=uninstall.exe /S=0K /G=0" $0 $1 $2
  IntOp $0 $0 + ${ESTIMATEDSIZE}
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD SHCTX "${UNINSTKEY}" "EstimatedSize" "$0"

  !if "${HOMEPAGE}" != ""
    WriteRegStr SHCTX "${UNINSTKEY}" "URLInfoAbout" "${HOMEPAGE}"
    WriteRegStr SHCTX "${UNINSTKEY}" "URLUpdateInfo" "${HOMEPAGE}"
    WriteRegStr SHCTX "${UNINSTKEY}" "HelpLink" "${HOMEPAGE}"
  !endif

  ; Create start menu shortcut
  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
    Call CreateOrUpdateStartMenuShortcut
  !insertmacro MUI_STARTMENU_WRITE_END

  ; Create desktop shortcut for silent and passive installers
  ; because finish page will be skipped
  ${If} $PassiveMode = 1
  ${OrIf} ${Silent}
    Call CreateOrUpdateDesktopShortcut
  ${EndIf}

  !ifmacrodef NSIS_HOOK_POSTINSTALL
    !insertmacro NSIS_HOOK_POSTINSTALL
  !endif

  ; Auto close this page for passive mode
  ${If} $PassiveMode = 1
    SetAutoClose true
  ${EndIf}
SectionEnd

Function .onInstSuccess
  ; Check for `/R` flag only in silent and passive installers because
  ; GUI installer has a toggle for the user to (re)start the app
  ${If} $PassiveMode = 1
  ${OrIf} ${Silent}
    ${GetOptions} $CMDLINE "/R" $R0
    ${IfNot} ${Errors}
      ${GetOptions} $CMDLINE "/ARGS" $R0
      nsis_tauri_utils::RunAsUser "$INSTDIR\${MAINBINARYNAME}.exe" "$R0"
    ${EndIf}
  ${EndIf}
FunctionEnd

Function un.onInit
  !insertmacro SetContext

  !if "${INSTALLMODE}" == "both"
    !insertmacro MULTIUSER_UNINIT
  !endif

  !insertmacro MUI_UNGETLANGUAGE

  ${GetOptions} $CMDLINE "/P" $PassiveMode
  ${IfNot} ${Errors}
    StrCpy $PassiveMode 1
  ${EndIf}

  ${GetOptions} $CMDLINE "/UPDATE" $UpdateMode
  ${IfNot} ${Errors}
    StrCpy $UpdateMode 1
  ${EndIf}
FunctionEnd

Section Uninstall

  !ifmacrodef NSIS_HOOK_PREUNINSTALL
    !insertmacro NSIS_HOOK_PREUNINSTALL
  !endif

  !insertmacro CheckIfAppIsRunning "$INSTDIR\${MAINBINARYNAME}.exe" "${PRODUCTNAME}"

  ; Delete the app directory and its content from disk
  ; Copy main executable
  Delete "$INSTDIR\${MAINBINARYNAME}.exe"

  ; Delete resources
    Delete "$INSTDIR\resources\backend\_internal\PIL\_avif.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\PIL\_imaging.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\PIL\_imagingcms.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\PIL\_imagingft.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\PIL\_imagingtk.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\PIL\_webp.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\VCRUNTIME140.dll"
    Delete "$INSTDIR\resources\backend\_internal\VCRUNTIME140_1.dll"
    Delete "$INSTDIR\resources\backend\_internal\_asyncio.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_bz2.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_ctypes.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_decimal.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_elementtree.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_hashlib.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_lzma.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_multiprocessing.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_overlapped.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_queue.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_socket.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_sqlite3.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_ssl.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_uuid.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_wmi.pyd"
    Delete "$INSTDIR\resources\backend\_internal\_zoneinfo.pyd"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-console-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-datetime-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-debug-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-errorhandling-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-fibers-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-fibers-l1-1-1.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-file-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-file-l1-2-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-file-l2-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-handle-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-heap-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-interlocked-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-kernel32-legacy-l1-1-1.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-libraryloader-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-localization-l1-2-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-memory-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-namedpipe-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-processenvironment-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-processthreads-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-processthreads-l1-1-1.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-profile-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-rtlsupport-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-string-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-synch-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-synch-l1-2-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-sysinfo-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-sysinfo-l1-2-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-timezone-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-core-util-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-conio-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-convert-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-environment-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-filesystem-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-heap-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-locale-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-math-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-private-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-process-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-runtime-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-stdio-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-string-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-time-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\api-ms-win-crt-utility-l1-1-0.dll"
    Delete "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info\INSTALLER"
    Delete "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info\METADATA"
    Delete "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info\RECORD"
    Delete "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info\REQUESTED"
    Delete "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info\WHEEL"
    Delete "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info\licenses\LICENSE"
    Delete "$INSTDIR\resources\backend\_internal\base_library.zip"
    Delete "$INSTDIR\resources\backend\_internal\certifi\cacert.pem"
    Delete "$INSTDIR\resources\backend\_internal\certifi\py.typed"
    Delete "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info\INSTALLER"
    Delete "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info\METADATA"
    Delete "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info\RECORD"
    Delete "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info\REQUESTED"
    Delete "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info\WHEEL"
    Delete "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info\licenses\LICENSE.txt"
    Delete "$INSTDIR\resources\backend\_internal\libcrypto-3-x64.dll"
    Delete "$INSTDIR\resources\backend\_internal\libffi-8.dll"
    Delete "$INSTDIR\resources\backend\_internal\libssl-3-x64.dll"
    Delete "$INSTDIR\resources\backend\_internal\numpy\_core\_multiarray_tests.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\_core\_multiarray_umath.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\fft\_pocketfft_umath.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\linalg\_umath_linalg.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\_bounded_integers.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\_common.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\_generator.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\_mt19937.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\_pcg64.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\_philox.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\_sfc64.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\bit_generator.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy\random\mtrand.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\DELVEWHEEL"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\INSTALLER"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\METADATA"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\RECORD"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\REQUESTED"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\WHEEL"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\entry_points.txt"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\LICENSE.txt"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\include\numpy\libdivide\LICENSE.txt"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\common\pythoncapi-compat\COPYING"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\highway\LICENSE"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\multiarray\dragon4_LICENSE.txt"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\npysort\x86-simd-sort\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\umath\svml\LICENSE"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\fft\pocketfft\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\linalg\lapack_lite\LICENSE.txt"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\ma\LICENSE"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\distributions\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\mt19937\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\pcg64\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\philox\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\sfc64\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\splitmix64\LICENSE.md"
    Delete "$INSTDIR\resources\backend\_internal\numpy.libs\libscipy_openblas64_-ed4f167a5330424524f45258e7ca2c8d.dll"
    Delete "$INSTDIR\resources\backend\_internal\numpy.libs\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll"
    Delete "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\INSTALLER"
    Delete "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\METADATA"
    Delete "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\RECORD"
    Delete "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\REQUESTED"
    Delete "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\WHEEL"
    Delete "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\entry_points.txt"
    Delete "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\licenses\LICENSE"
    Delete "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\INSTALLER"
    Delete "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\METADATA"
    Delete "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\RECORD"
    Delete "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\REQUESTED"
    Delete "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\WHEEL"
    Delete "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\licenses\LICENSE"
    Delete "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\top_level.txt"
    Delete "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info\INSTALLER"
    Delete "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info\METADATA"
    Delete "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info\RECORD"
    Delete "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info\REQUESTED"
    Delete "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info\WHEEL"
    Delete "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info\licenses\LICENSE"
    Delete "$INSTDIR\resources\backend\_internal\pydantic_core\_pydantic_core.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\pyexpat.pyd"
    Delete "$INSTDIR\resources\backend\_internal\python312.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_base.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_base.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_base.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_base.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_env.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_env.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_env.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_env.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_err.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_err.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_err.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_err.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_example.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_example.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_example.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_features.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_features.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_features.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_features.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_filepath.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_filepath.cpp"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_filepath.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_filepath.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_fill.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_fill.cpp"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_fill.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_io.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_io.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_io.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_io.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_transform.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_transform.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_transform.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_version.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_version.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_version.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_version.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_vsiopener.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_vsiopener.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_vsiopener.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_vsiopener.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_warp.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_warp.cpp"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_warp.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\_warp.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\cache.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\cache.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\cache.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\crs.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\crs.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\crs.pxd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\crs.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal.pxi"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\GDAL-targets-debug.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\GDAL-targets-release.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\GDAL-targets.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\GDALConfig.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\GDALConfigVersion.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\GDALLogoBW.svg"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\GDALLogoColor.svg"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\GDALLogoGS.svg"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\LICENSE.TXT"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\MM_m_idofic.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\bag_template.xml"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\copyright"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\cubewerx_extra.wkt"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\default.rsc"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ecw_cs.wkt"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\eedaconf.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\epsg.wkt"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\esri_StatePlane_extra.wkt"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gdal_algorithm.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gdalg.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gdalicon.png"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gdalinfo_output.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gdalmdiminfo_output.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gdaltileindex.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gdalvrt.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gfs.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gml_registry.xml"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gml_registry.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_center.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_process.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_subcenter.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_0.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_1.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_13.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_14.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_15.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_16.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_17.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_18.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_19.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_190.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_191.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_2.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_20.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_21.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_22.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_3.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_4.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_5.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_6.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_0_7.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_0.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_1.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_191.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_2.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_3.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_10_4.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_0.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_1.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_1_2.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_0.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_1.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_2.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_20_3.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_0.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_3.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_4.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_5.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_6.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_2_7.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_0.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_1.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_2.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_3.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_4.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_5.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_3_6.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_0.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_1.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_10.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_2.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_3.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_4.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_5.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_6.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_7.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_8.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_4_9.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_Canada.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_HPC.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_MRMS.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_NCEP.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_NDFD.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_2_local_index.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_4_5.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\grib2_table_versions.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gt_datum.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\gt_ellips.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\header.dxf"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\inspire_cp_BasicPropertyUnit.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralBoundary.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralParcel.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\inspire_cp_CadastralZoning.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmArea.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmBdry.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_AdmPt.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_BldA.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_BldL.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_Cntr.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_CommBdry.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_CommPt.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_Cstline.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_ElevPt.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_GCP.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_LeveeEdge.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RailCL.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdASL.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdArea.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdCompt.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdEdg.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdMgtBdry.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RdSgmtA.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_RvrMgtBdry.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBAPt.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBArea.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_SBBdry.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WA.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WL.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WStrA.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\jpfgdgml_WStrL.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\leaflet_template.html"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\netcdf_config.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\nitf_spec.xml"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\nitf_spec.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ogr_fields_override.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ogrinfo_output.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ogrvrt.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\osmconf.ini"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ozi_datum.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ozi_ellips.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\pci_datum.txt"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\pci_ellips.txt"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\pdfcomposition.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\pds4_template.xml"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\plscenesconf.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ruian_vf_ob_v1.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ruian_vf_st_uvoh_v1.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ruian_vf_st_v1.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\ruian_vf_v1.gfs"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\s57agencies.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\s57attributes.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\s57expectedinput.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\s57objectclasses.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\seed_2d.dgn"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\seed_3d.dgn"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\stateplane.csv"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\template_tiles.mapml"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\tms_LINZAntarticaMapTileGrid.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\tms_MapML_APSTILE.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\tms_MapML_CBMTILE.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\tms_NZTM2000.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\trailer.dxf"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\usage"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\vcpkg-cmake-wrapper.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\vcpkg-spdx-resources.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\vcpkg.spdx.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\vcpkg_abi_info.txt"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\vdv452.xml"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\vdv452.xsd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\gdal_data\vicar.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\CH"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\GL27"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\ITRF2000"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\ITRF2008"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\ITRF2014"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\ITRF2020"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\copyright"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\deformation_model.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\nad.lst"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\nad27"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\nad83"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\other.extra"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj-config-version.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj-config.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj-targets-debug.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj-targets-release.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj-targets.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj.db"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj.ini"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj4-targets-debug.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj4-targets-release.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\proj4-targets.cmake"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\projjson.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\triangulation.schema.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\usage"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\vcpkg-spdx-resources.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\vcpkg.spdx.json"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\vcpkg_abi_info.txt"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\proj_data\world"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\shutil.c"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\shutil.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\rasterio\shutil.pyx"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\Lerc-bd596e02be0e2a4d97970986d405b306.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\freexl-1-f984fed45cb40bcf96e583a5d17e3e9f.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\gdal-ca23e679e52f19649323f953f4a92966.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\geos-353ca83806e765757ee1ac85230fad94.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\geos_c-ee1211e77d58bd95402e455720af8ce9.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\geotiff-5e33421f0ae45bc20fe26c869841819c.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\gif-1107c2c29ae9bc2dab88f8650eedf346.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\hdf5-90d65e8c6734fd05e7f71019aea56e63.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\hdf5_hl-0f04f4391d2304f0c3baecb4b64cc3c7.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\iconv-2-ebb8d125e8964d978f001ad727bb1f6a.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\jpeg62-f01e7c07b88707d3293da417a2270e8d.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\json-c-69add94c2356636200f46910429b496e.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libcrypto-3-x64-2afd3870ac1ca9227daaf71022d519dd.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libcurl-59fd99b636208c0efd91cad8b4cf028c.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libexpat-533441caabb6e8e810f3c428aac8662a.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\liblzma-493fcad0ab8b3babd9c41dbd94a1afe5.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libpng16-644a70bf72a6c164e16c88d6a0c64f5b.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libpq-95c240938b5ffe9f0191160d951f9302.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libsharpyuv-39f8caaabd4dd845629ed7064c22149b.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libssl-3-x64-cdfaf2036db9847e1470a7adabf3576a.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libwebp-c62a0ecd823a4ac55d020b1e5b4e214d.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\libxml2-ee3a45b6842891635a7194ed3bf4439b.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\minizip-a17a1f1144c99133fb8ac04c5fc0d727.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\netcdf-80fff5a18c54bb9f3a649624658cc0ae.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\openjp2-c1951c6e297b4dfbc1ecfed46df803af.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\pcre2-8-4250f3875b7c8017370f480e5933b922.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\proj_9-d142a65602e419d49589809f8c96ed95.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\qhull_r-9dfe5950fe3ffbeff1f83f37ef8a3b6a.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\spatialite-462100c3ae387a5046878044decbecb9.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\sqlite3-a95e23ad82678982e28e9780f07ae1f7.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\szip-237b7e7db63858546dc0b6d1d1113e6c.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\tiff-ab336932b464eb213b8c0ba892721190.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\tinyxml2-b1394948d9bf11d7822da2aabdf5ab40.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\zlib1-63e59a7591925180e9af63ff1cf293fb.dll"
    Delete "$INSTDIR\resources\backend\_internal\rasterio.libs\zstd-2363c320dd62f9f202293b4b1406aac1.dll"
    Delete "$INSTDIR\resources\backend\_internal\scipy\_cyutility.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\_lib\_ccallback_c.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\_lib\_fpumode.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\_lib\_uarray\_uarray.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\_lib\messagestream.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\fft\_duccfft\pyduccfft.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\integrate\_dop.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\integrate\_odepack.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\integrate\_quadpack.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\integrate\_vode.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\interpolate\_dierckx.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\interpolate\_fitpack.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\interpolate\_interpnd.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\interpolate\_ppoly.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\interpolate\_rbfinterp_pythran.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\interpolate\_rgi_cython.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_batched_linalg.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_cythonized_array_utils.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_decomp_interpolative.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_decomp_update.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_fblas.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_flapack.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_internal_matfuncs.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_linalg_pythran.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_matfuncs_sqrtm_triu.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\_solve_toeplitz.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\cython_blas.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\linalg\cython_lapack.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\ndimage\_nd_image.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\ndimage\_ni_label.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\ndimage\_rank_filter_1d.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_bglu_dense.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_direct.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_group_columns.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_highspy\_core.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_highspy\_highs_options.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_lbfgsb.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_lsap.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_lsq\givens_elimination.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_minpack.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_moduleTNC.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_pava_pybind.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_slsqplib.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_trlib\_trlib.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\optimize\_zeros.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\_csparsetools.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\_sparsetools.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph\_flow.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph\_matching.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph\_min_spanning_tree.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph\_reordering.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph\_shortest_path.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph\_tools.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph\_traversal.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg\_dsolve\_superlu.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg\_eigen\arpack\_arpacklib.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg\_propack.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\spatial\_ckdtree.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\spatial\_distance_pybind.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\spatial\_distance_wrap.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\spatial\_hausdorff.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\spatial\_qhull.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\spatial\_voronoi.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\spatial\transform\_rigid_transform_cy.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\spatial\transform\_rotation_cy.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\special\_comb.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\special\_ellip_harm_2.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\special\_gufuncs.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\special\_specfun.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\special\_special_ufuncs.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\special\_ufuncs.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\special\_ufuncs_cxx.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\special\cython_special.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_ansari_swilk_statistics.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_biasedurn.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_levy_stable\levyst.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_qmc_cy.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_qmvnt_cy.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_rcont\rcont.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_sobol.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_stats.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy\stats\_stats_pythran.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\scipy.libs\libscipy_openblas-197ee2fc9b4d071f7e048078cac74115.dll"
    Delete "$INSTDIR\resources\backend\_internal\select.pyd"
    Delete "$INSTDIR\resources\backend\_internal\setuptools\_vendor\jaraco\text\Lorem ipsum.txt"
    Delete "$INSTDIR\resources\backend\_internal\sqlite3.dll"
    Delete "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\INSTALLER"
    Delete "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\METADATA"
    Delete "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\RECORD"
    Delete "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\REQUESTED"
    Delete "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\WHEEL"
    Delete "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\licenses\LICENSE-APACHE"
    Delete "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\licenses\LICENSE-MIT"
    Delete "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\licenses\NOTICE"
    Delete "$INSTDIR\resources\backend\_internal\ucrtbase.dll"
    Delete "$INSTDIR\resources\backend\_internal\unicodedata.pyd"
    Delete "$INSTDIR\resources\backend\_internal\websockets\speedups.cp312-win_amd64.pyd"
    Delete "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\INSTALLER"
    Delete "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\METADATA"
    Delete "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\RECORD"
    Delete "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\REQUESTED"
    Delete "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\WHEEL"
    Delete "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\entry_points.txt"
    Delete "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\licenses\LICENSE"
    Delete "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\top_level.txt"
    Delete "$INSTDIR\resources\backend\app.exe"

  ; Delete external binaries

  ; Delete app associations

  ; Delete deep links


  ; Delete uninstaller
  Delete "$INSTDIR\uninstall.exe"

  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\include\numpy\libdivide"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\common\pythoncapi-compat"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\npysort\x86-simd-sort"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\umath\svml"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\include\numpy"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\common"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\highway"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\multiarray"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\npysort"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src\umath"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\distributions"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\mt19937"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\pcg64"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\philox"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\sfc64"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src\splitmix64"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\include"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core\src"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\fft\pocketfft"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\linalg\lapack_lite"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random\src"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg\_eigen\arpack"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\_core"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\fft"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\linalg"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\ma"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy\random"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg\_dsolve"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg\_eigen"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\setuptools\_vendor\jaraco\text"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses\numpy"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\_lib\_uarray"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\fft\_duccfft"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\optimize\_highspy"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\optimize\_lsq"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\optimize\_trlib"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\sparse\csgraph"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\sparse\linalg"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\spatial\transform"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\stats\_levy_stable"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\stats\_rcont"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\setuptools\_vendor\jaraco"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info\licenses"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info\licenses"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy\_core"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy\fft"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy\linalg"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy\random"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info\licenses"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info\licenses"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info\licenses"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info\licenses"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\rasterio\gdal_data"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\rasterio\proj_data"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\_lib"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\fft"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\integrate"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\interpolate"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\linalg"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\ndimage"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\optimize"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\sparse"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\spatial"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\special"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy\stats"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\setuptools\_vendor"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info\licenses"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info\licenses"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\PIL"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\attrs-26.1.0.dist-info"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\certifi"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\click-8.5.0.dist-info"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy-2.5.4.dist-info"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\numpy.libs"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\opentelemetry_api-1.45.1.dist-info"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\pluggy-1.7.0.dist-info"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\pydantic-2.14.1.dist-info"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\pydantic_core"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\rasterio"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\rasterio.libs"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\scipy.libs"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\setuptools"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\structlog-26.1.0.dist-info"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\websockets"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal\websockets-17.2.dist-info"
  RMDir /REBOOTOK "$INSTDIR\resources\backend\_internal"
  RMDir /REBOOTOK "$INSTDIR\resources\backend"
  RMDir /REBOOTOK "$INSTDIR\resources"
  RMDir "$INSTDIR"

  ; Remove shortcuts if not updating
  ${If} $UpdateMode <> 1
    !insertmacro DeleteAppUserModelId

    ; Remove start menu shortcut
    !insertmacro MUI_STARTMENU_GETFOLDER Application $AppStartMenuFolder
    !insertmacro IsShortcutTarget "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    Pop $0
    ${If} $0 = 1
      !insertmacro UnpinShortcut "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"
      Delete "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"
      RMDir "$SMPROGRAMS\$AppStartMenuFolder"
    ${EndIf}
    !insertmacro IsShortcutTarget "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    Pop $0
    ${If} $0 = 1
      !insertmacro UnpinShortcut "$SMPROGRAMS\${PRODUCTNAME}.lnk"
      Delete "$SMPROGRAMS\${PRODUCTNAME}.lnk"
    ${EndIf}

    ; Remove desktop shortcuts
    !insertmacro IsShortcutTarget "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    Pop $0
    ${If} $0 = 1
      !insertmacro UnpinShortcut "$DESKTOP\${PRODUCTNAME}.lnk"
      Delete "$DESKTOP\${PRODUCTNAME}.lnk"
    ${EndIf}
  ${EndIf}

  ; Remove registry information for add/remove programs
  !if "${INSTALLMODE}" == "both"
    DeleteRegKey SHCTX "${UNINSTKEY}"
  !else if "${INSTALLMODE}" == "perMachine"
    DeleteRegKey HKLM "${UNINSTKEY}"
  !else
    DeleteRegKey HKCU "${UNINSTKEY}"
  !endif

  ; Removes the Autostart entry for ${PRODUCTNAME} from the HKCU Run key if it exists.
  ; This ensures the program does not launch automatically after uninstallation if it exists.
  ; If it doesn't exist, it does nothing.
  ; We do this when not updating (to preserve the registry value on updates)
  ${If} $UpdateMode <> 1
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCTNAME}"
  ${EndIf}

  ; Delete app data if the checkbox is selected
  ; and if not updating
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    ; Clear the install location $INSTDIR from registry
    DeleteRegKey SHCTX "${MANUPRODUCTKEY}"
    DeleteRegKey /ifempty SHCTX "${MANUKEY}"

    ; Clear the install language from registry
    DeleteRegValue HKCU "${MANUPRODUCTKEY}" "Installer Language"
    DeleteRegKey /ifempty HKCU "${MANUPRODUCTKEY}"
    DeleteRegKey /ifempty HKCU "${MANUKEY}"

    SetShellVarContext current
    RmDir /r "$APPDATA\${BUNDLEID}"
    RmDir /r "$LOCALAPPDATA\${BUNDLEID}"
  ${EndIf}

  !ifmacrodef NSIS_HOOK_POSTUNINSTALL
    !insertmacro NSIS_HOOK_POSTUNINSTALL
  !endif

  ; Auto close if passive mode or updating
  ${If} $PassiveMode = 1
  ${OrIf} $UpdateMode = 1
    SetAutoClose true
  ${EndIf}
SectionEnd

Function RestorePreviousInstallLocation
  ReadRegStr $4 SHCTX "${MANUPRODUCTKEY}" ""
  StrCmp $4 "" +2 0
    StrCpy $INSTDIR $4
FunctionEnd

Function Skip
  Abort
FunctionEnd

Function SkipIfPassive
  ${IfThen} $PassiveMode = 1  ${|} Abort ${|}
FunctionEnd
Function un.SkipIfPassive
  ${IfThen} $PassiveMode = 1  ${|} Abort ${|}
FunctionEnd

Function CreateOrUpdateStartMenuShortcut
  ; We used to use product name as MAINBINARYNAME
  ; migrate old shortcuts to target the new MAINBINARYNAME
  StrCpy $R0 0

  !insertmacro IsShortcutTarget "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\$OldMainBinaryName"
  Pop $0
  ${If} $0 = 1
    !insertmacro SetShortcutTarget "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    StrCpy $R0 1
  ${EndIf}

  !insertmacro IsShortcutTarget "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\$OldMainBinaryName"
  Pop $0
  ${If} $0 = 1
    !insertmacro SetShortcutTarget "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    StrCpy $R0 1
  ${EndIf}

  ${If} $R0 = 1
    Return
  ${EndIf}

  ; Skip creating shortcut if in update mode or no shortcut mode
  ; but always create if migrating from wix
  ${If} $WixMode = 0
    ${If} $UpdateMode = 1
    ${OrIf} $NoShortcutMode = 1
      Return
    ${EndIf}
  ${EndIf}

  !if "${STARTMENUFOLDER}" != ""
    CreateDirectory "$SMPROGRAMS\$AppStartMenuFolder"
    CreateShortcut "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    !insertmacro SetLnkAppUserModelId "$SMPROGRAMS\$AppStartMenuFolder\${PRODUCTNAME}.lnk"
  !else
    CreateShortcut "$SMPROGRAMS\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    !insertmacro SetLnkAppUserModelId "$SMPROGRAMS\${PRODUCTNAME}.lnk"
  !endif
FunctionEnd

Function CreateOrUpdateDesktopShortcut
  ; We used to use product name as MAINBINARYNAME
  ; migrate old shortcuts to target the new MAINBINARYNAME
  !insertmacro IsShortcutTarget "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\$OldMainBinaryName"
  Pop $0
  ${If} $0 = 1
    !insertmacro SetShortcutTarget "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
    Return
  ${EndIf}

  ; Skip creating shortcut if in update mode or no shortcut mode
  ; but always create if migrating from wix
  ${If} $WixMode = 0
    ${If} $UpdateMode = 1
    ${OrIf} $NoShortcutMode = 1
      Return
    ${EndIf}
  ${EndIf}

  CreateShortcut "$DESKTOP\${PRODUCTNAME}.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
  !insertmacro SetLnkAppUserModelId "$DESKTOP\${PRODUCTNAME}.lnk"
FunctionEnd
