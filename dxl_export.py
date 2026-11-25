def quote(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('\r\n','\n').replace('\r','\n').replace('\n', '\\n').replace('\t', '\\t') + '"'

def generate(items):
    if not items: raise ValueError('没有可导出的需求')
    lines = ['// DOORS Classic 9.7.2: use an empty test module.', 'Module m = current', 'if (null m) { ack "Open an empty test module first."; halt }', 'Object existing = first m', 'if (!null existing) { ack "Module is not empty. Import stopped."; halt }', 'if (!confirm "Create objects in this empty test module?" ) { halt }']
    previous = []
    for i, item in enumerate(items):
        level = item['level']
        if not isinstance(level,int) or level < 0 or level > len(previous): raise ValueError(f'第 {i+1} 条层级无效')
        if i == 0:
            if level != 0: raise ValueError('第一条必须为顶层')
            create = 'create m'
        elif level == len(previous): create = f'create below obj{previous[-1]}'
        else: create = f'create after obj{previous[level]}'
        lines.extend([f'Object obj{i} = {create}', f'obj{i}."Object Text" = {quote(item["text"])}'])
        previous = previous[:level] + [i]
    lines.append('ack "Import complete. Review the objects and save the module."')
    return '\r\n'.join(lines) + '\r\n'

def write_script(path,items):
    script=generate(items)
    data=script.encode('mbcs',errors='strict')
    with open(path,'wb') as output: output.write(data)
