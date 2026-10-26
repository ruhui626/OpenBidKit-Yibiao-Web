param([Parameter(Mandatory=$true)][string]$Manifest, [Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetGenericArguments().Count -eq 1 } | Select-Object -First 1
function Await-WinRt($Operation, [Type]$ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(30000)) { throw 'OCR operation timed out' }
    $task.GetAwaiter().GetResult()
}
$language = [Windows.Globalization.Language]::new('zh-Hans-CN')
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) { throw 'Simplified Chinese OCR is unavailable' }
$jobs = Get-Content -Raw -LiteralPath $Manifest -Encoding UTF8 | ConvertFrom-Json
$results = @()
foreach ($job in $jobs) {
    $stream = $null
    $bitmap = $null
    try {
        $file = Await-WinRt ([Windows.Storage.StorageFile]::GetFileFromPathAsync([IO.Path]::GetFullPath($job.path))) ([Windows.Storage.StorageFile])
        $stream = Await-WinRt ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await-WinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-WinRt ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        if ($bitmap.PixelWidth -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension -or $bitmap.PixelHeight -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) { throw 'Image exceeds OCR dimension limit' }
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $result = Await-WinRt ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $watch.Stop()
        $lines = @()
        foreach ($line in $result.Lines) {
            $words = @()
            foreach ($word in $line.Words) {
                $rect = $word.BoundingRect
                $words += [ordered]@{ text=$word.Text; rect=@([double]$rect.X,[double]$rect.Y,[double]$rect.Width,[double]$rect.Height) }
            }
            $lines += [ordered]@{ text=$line.Text; words=$words }
        }
        $results += [ordered]@{ id=$job.id; ok=$true; width=$bitmap.PixelWidth; height=$bitmap.PixelHeight; text=$result.Text; textAngle=$result.TextAngle; lines=$lines; confidence=$null; elapsedMs=$watch.ElapsedMilliseconds }
    } catch {
        $results += [ordered]@{ id=$job.id; ok=$false; error=$_.Exception.Message }
    } finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}
$payload = [ordered]@{engine='Windows.Media.Ocr'; language=$engine.RecognizerLanguage.LanguageTag; maxImageDimension=[Windows.Media.Ocr.OcrEngine]::MaxImageDimension; results=$results}
[IO.File]::WriteAllText($Output, (ConvertTo-Json -Depth 15 -InputObject $payload), [Text.UTF8Encoding]::new($false))
Write-Output ('OCR inputs: ' + $results.Count)
