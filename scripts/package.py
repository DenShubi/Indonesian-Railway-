import zipfile, pathlib
G=pathlib.Path('/home/claude/jtv/gtfs'); D=pathlib.Path('/home/claude/jtv/data')
zp=D/'gtfs_wilayah8_surabaya.zip'
with zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED) as z:
    for f in sorted(G.glob('*.txt')): z.write(f,f.name)
print("packaged:",zp.name,zp.stat().st_size,"bytes")
for f in sorted(G.glob('*.txt')): print(f"   {f.name:<16}{sum(1 for _ in open(f))-1:>6} rows")
