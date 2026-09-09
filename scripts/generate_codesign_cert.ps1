<#
.SYNOPSIS
    Generates a self-signed Authenticode code-signing certificate for PowerDim
    releases, and exports it as a base64 string ready to paste into a GitHub
    Actions secret.

.DESCRIPTION
    Run this yourself, locally, in your own PowerShell window -- do not paste
    its output into a chat/AI tool. The exported .pfx contains your private
    signing key; anyone with it (and the password) can sign files as "you."

    This is a SELF-SIGNED certificate: Windows SmartScreen and antivirus will
    still show "Unknown Publisher" warnings for anything signed with it. Its
    purpose here is narrower -- it lets PowerDim's own updater verify that a
    downloaded update was signed with the exact same key as previous builds,
    as a defense-in-depth check on top of the checksum verification, not to
    get rid of Windows' publisher-trust warnings.

.NOTES
    After running this script:
      1. Go to your GitHub repo -> Settings -> Secrets and variables -> Actions.
      2. Add a secret named CODESIGN_PFX_BASE64 with the base64 text printed
         below (or read from codesign.pfx.base64.txt).
      3. Add a secret named CODESIGN_PASSWORD with the password you enter below.
      4. Copy the printed certificate thumbprint into
         EXPECTED_SIGNER_THUMBPRINT in powerdim/updater.py and commit that.
      5. Delete the local .pfx file (and the .txt) once both secrets are saved
         -- they don't need to stay on disk after that.
#>

$password = Read-Host -AsSecureString -Prompt "Enter a password to protect the exported .pfx"

$cert = New-SelfSignedCertificate `
    -Subject "CN=PowerDim" `
    -Type CodeSigningCert `
    -KeyUsage DigitalSignature `
    -FriendlyName "PowerDim Code Signing" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears(5)

$pfxPath = Join-Path $PSScriptRoot "codesign.pfx"
Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $password | Out-Null

$base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($pfxPath))
$base64Path = Join-Path $PSScriptRoot "codesign.pfx.base64.txt"
Set-Content -Path $base64Path -Value $base64 -NoNewline

Write-Host ""
Write-Host "Certificate thumbprint (put this in powerdim/updater.py):" -ForegroundColor Cyan
Write-Host $cert.Thumbprint
Write-Host ""
Write-Host "Base64 .pfx written to: $base64Path" -ForegroundColor Cyan
Write-Host "Paste its contents into the CODESIGN_PFX_BASE64 GitHub secret," -ForegroundColor Cyan
Write-Host "and the password you entered above into CODESIGN_PASSWORD." -ForegroundColor Cyan
Write-Host ""
Write-Host "Once both secrets are saved, delete $pfxPath and $base64Path." -ForegroundColor Yellow
