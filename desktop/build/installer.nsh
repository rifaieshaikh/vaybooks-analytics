!macro customInit
  ExecWait 'taskkill /F /IM "Vay Reports.exe" /T'
  ExecWait 'taskkill /F /IM "vay-api.exe" /T'
!macroend

!macro customInstall
  ExecWait 'netsh advfirewall firewall delete rule name="Vay Reports"'
  ExecWait 'netsh advfirewall firewall add rule name="Vay Reports" dir=in action=allow protocol=TCP localport=8765 profile=any'
!macroend

!macro customUnInstall
  ExecWait 'netsh advfirewall firewall delete rule name="Vay Reports"'
!macroend
