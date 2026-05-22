"""Deduplicate and clean the output Excel file"""
import pandas as pd

INPUT = "matched_papers.xlsx"
OUTPUT = "matched_papers_clean.xlsx"

df = pd.read_excel(INPUT)
print(f"Before: {len(df)} rows")

# Deduplicate by 控制号 + 论文标题
df = df.drop_duplicates(subset=['控制号','论文标题'], keep='first')
print(f"After dedup: {len(df)} rows")

# Filter out "无" institution profiles
df = df[df['种子单位'] != '无']
print(f"After removing '无': {len(df)} rows")

# Clean institution field: remove abstract text mistakenly extracted as institution
def clean_inst(val):
    if pd.isna(val) or not isinstance(val, str):
        return val
    if val.startswith('摘要') or len(val) > 300:
        return ''
    return val

df['论文机构'] = df['论文机构'].apply(clean_inst)
empty_after = (df['论文机构'].isna() | (df['论文机构'] == '')).sum()
print(f"Cleaned institution (empty now): {empty_after}")

df.to_excel(OUTPUT, index=False)

print(f"\nFinal: {len(df)} rows")
print(f"Unique profiles: {df['控制号'].nunique()}")
print(f"Unique institutions: {df['种子单位'].nunique()}")
print(f"Saved to: {OUTPUT}")
