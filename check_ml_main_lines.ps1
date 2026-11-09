$m = Get-Content -Encoding UTF8 src\main.py
"==== settings and sidebar lines"
Select-String -Path src\main.py -Pattern 'st\.sidebar|use_knowledge|use_gemini|use_sentiment|current_settings|knowledge_role|knowledge_region' | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line }
"==== lines 325-363"
for ($i = 325; $i -le 363; $i++) { "{0}: {1}" -f $i, $m[$i-1] }
"==== lines 376-401"
for ($i = 376; $i -le 401; $i++) { "{0}: {1}" -f $i, $m[$i-1] }
"==== lines 460-" + $m.Count
for ($i = 460; $i -le $m.Count; $i++) { "{0}: {1}" -f $i, $m[$i-1] }
"==== documentation files"
Get-ChildItem README.md, .env.example, TASK*_NOTES.md | Select-Object Name, Length
"==== README headings"
Select-String -Path README.md -Pattern '^#' | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line }
"==== .env.example Task 5 lines"
Select-String -Path .env.example -Pattern 'SENTIMENT|TICKET' | ForEach-Object { $_.Line }