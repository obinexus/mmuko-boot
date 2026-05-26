$ErrorActionPreference = "Stop"

$build = Join-Path $PSScriptRoot "build"
New-Item -ItemType Directory -Force -Path $build | Out-Null

$bootObj = Join-Path $build "boot16.o"
$bootPe = Join-Path $build "boot16.pe"
$bootBin = Join-Path $build "boot.bin"
$entryObj = Join-Path $build "kernel-entry.o"
$kernelObj = Join-Path $build "kernel.o"
$kernelPe = Join-Path $build "kernel-flat.pe"
$kernelBin = Join-Path $build "kernel-flat.bin"
$image = Join-Path $build "mmuko-direct.img"

& as --32 "$PSScriptRoot\boot16.s" -o $bootObj
& ld -m i386pe -Ttext 0x7C00 -o $bootPe $bootObj
& objcopy -O binary -j .text $bootPe $bootBin

$bootLength = (Get-Item $bootBin).Length
if ($bootLength -lt 512) {
    throw "Boot sector must be at least 512 bytes, got $bootLength"
}
if ($bootLength -gt 512) {
    $bootBytesForTrim = [System.IO.File]::ReadAllBytes($bootBin)
    $trimmedBoot = New-Object byte[] 512
    [Array]::Copy($bootBytesForTrim, 0, $trimmedBoot, 0, 512)
    [System.IO.File]::WriteAllBytes($bootBin, $trimmedBoot)
    $bootLength = 512
}

$bootCheck = [System.IO.File]::ReadAllBytes($bootBin)
if ($bootCheck[510] -ne 0x55 -or $bootCheck[511] -ne 0xAA) {
    throw "Boot sector is missing the 0x55AA signature"
}

& as --32 "$PSScriptRoot\kernel-entry.s" -o $entryObj
& gcc -m32 -std=gnu11 -ffreestanding -O2 -Wall -Wextra -fno-pic -fno-pie -fno-stack-protector -c "$PSScriptRoot\kernel.c" -o $kernelObj
& ld -m i386pe -T "$PSScriptRoot\linker-flat.ld" -o $kernelPe $entryObj $kernelObj
& objcopy -O binary $kernelPe $kernelBin

$kernelBytes = [System.IO.File]::ReadAllBytes($kernelBin)
$kernelSectorBytes = 64 * 512
if ($kernelBytes.Length -gt $kernelSectorBytes) {
    throw "Kernel is $($kernelBytes.Length) bytes; direct boot loader only reads $kernelSectorBytes bytes"
}

$bootBytes = [System.IO.File]::ReadAllBytes($bootBin)
$kernelArea = New-Object byte[] $kernelSectorBytes
[Array]::Copy($kernelBytes, 0, $kernelArea, 0, $kernelBytes.Length)

$imageBytes = New-Object byte[] (512 + $kernelSectorBytes)
[Array]::Copy($bootBytes, 0, $imageBytes, 0, 512)
[Array]::Copy($kernelArea, 0, $imageBytes, 512, $kernelSectorBytes)
[System.IO.File]::WriteAllBytes($image, $imageBytes)

Write-Host "Built $image"
Write-Host "Kernel bytes: $($kernelBytes.Length)"
Write-Host "Run:"
Write-Host "qemu-system-i386 -drive format=raw,file=$image,if=ide,index=0 -display none -serial stdio -no-reboot"
