
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "C:\Users\threeyang\Desktop\GoActivity 管理器.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "C:\Users\threeyang\AppData\Local\Programs\Python\Python314\pythonw.exe"
oLink.Arguments = "E:\cctry\GoActivity\gui_manager.py"
oLink.WorkingDirectory = "E:\cctry\GoActivity"
oLink.Description = "GoActivity 系统托盘管理器"
oLink.WindowStyle = 7
oLink.Save
