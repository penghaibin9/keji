# Does not install a CA, change firewall rules or store credentials.
$ErrorActionPreference = 'Stop'
$Server = Read-Host '请输入服务器SSH地址（只填IP或域名）'
$UserName = Read-Host '请输入SSH用户名'
$SshPort = Read-Host 'SSH端口（回车使用22）'
if (-not $SshPort) { $SshPort = '22' }
$Port = Read-Host '演示端口（以预检报告为准，回车使用18443）'
if (-not $Port) { $Port = '18443' }
if ($Server -notmatch '^[a-zA-Z0-9.-]+$' -or $UserName -notmatch '^[a-zA-Z0-9_-]+$' -or $Port -notmatch '^\d{4,5}$' -or $SshPort -notmatch '^\d{1,5}$') { throw '输入格式不正确' }
Write-Host ('建立隧道后访问：https://127.0.0.1:{0}' -f $Port)
Write-Host '首次访问前，请核对并手工信任该实例的R11_Local_CA.cer；不要关闭证书校验。'
Write-Host '保持本窗口打开。关闭本窗口即断开本机访问，不会停止服务器或删除数据。'
$Forward = '127.0.0.1:{0}:127.0.0.1:{0}' -f $Port
& ssh -N -p $SshPort -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L $Forward ($UserName+'@'+$Server)
