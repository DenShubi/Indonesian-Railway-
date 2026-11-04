import zipfile, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
G=ROOT/'gtfs'; D=ROOT/'data'
zp=D/'gtfs_java_commuter.zip'
with zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED) as z:
    for f in sorted(G.glob('*.txt')): z.write(f,f.name)
print("packaged:",zp.name,zp.stat().st_size,"bytes")
for f in sorted(G.glob('*.txt')): print(f"   {f.name:<16}{sum(1 for _ in open(f))-1:>6} rows")
