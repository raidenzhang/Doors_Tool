from pathlib import Path

def parse_files(paths, gap, indent):
    import fitz
    results=[]
    for path in paths:
        with fitz.open(path) as doc:
            for number,page in enumerate(doc,1):
                lines=[]
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines',[]):
                        text=''.join(span['text'] for span in line['spans']).strip()
                        if text: lines.append((line['bbox'],text))
                lines.sort(key=lambda x:(round(x[0][1],1),x[0][0]))
                if not lines: continue
                base=min(box[0] for box,_ in lines)
                previous=None
                for box,text in lines:
                    level=max(0,round((box[0]-base)/indent))
                    source=f'{Path(path).name}:{number}'
                    if previous and abs(box[0]-previous[0]) < indent/2 and 0 <= box[1]-previous[3] <= gap:
                        results[-1]['text'] += '\n'+text
                    else:
                        results.append(dict(text=text,level=level,page=source,uncertain=True))
                    previous=box
    return results
