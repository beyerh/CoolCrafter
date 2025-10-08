Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located
strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Change to the script directory and run Python
objShell.CurrentDirectory = strScriptDir
objShell.Run "python gui.py", 0, False
