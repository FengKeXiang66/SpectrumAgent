"""Local presentation of inference settings. These fields never drive execution."""
def number(value):
    return f'{value:.6g}'


def pipeline(steps):
    names = {'l2':'L2 归一化','center':'中心化','standard_scale':'标准化','snv':'SNV'}
    derivatives = {0:'SG 平滑',1:'SG 一阶导',2:'SG 二阶导'}
    parts = []
    for step in steps:
        op = step['op']
        if op == 'savgol':
            parts.append(f"{derivatives[step['derivative']]} (W{step['window']}, {step['polyorder']}阶, Δ{number(step['delta_nm'])} nm)")
        elif op == 'pca':
            parts.append(f"PCA ({step['n_components']} 分量)")
        else:
            parts.append(names.get(op,op))
    return ' → '.join(parts) or '无额外预处理'


def display_groups(document, model, waiting=False):
    spec = document.get('input', {})
    groups = {}

    def field(group, label, values, key, show=str):
        if key in values:
            value = values[key]
            groups.setdefault(group, {})[label] = (value, show(value))

    field('模型与输入','归档模型',document,'model_id',
          lambda value:f"{model['name']} · {value[:8]}" if model else value[:8])
    field('模型与输入','输入格式',spec,'kind',lambda value:{'npz':'NPZ 光谱','envi':'ENVI 原图'}.get(value,value))
    field('模型与输入','输入源',spec,'source_refs','、'.join)
    unit = {'center_pixel':'中心像元','spectrum':'光谱样本'}
    common = {**model, **spec}
    field('模型与输入','空间邻域',common,'neighborhood',lambda value:f'{value} × {value}')
    field('模型与输入','评价单位',common,'evaluation_unit',lambda value:unit.get(value,value))
    field('模型与输入','光谱字段',spec,'spectra_key')
    field('模型与输入','波长字段',spec,'wavelengths_key')
    field('模型与输入','输入阶段',spec,'input_stage',lambda value:{
        'spectra':'未做空间均值的光谱','neighborhood_mean':'已完成邻域均值的光谱'}.get(value,value))
    field('模型与输入','排除规则引用',spec,'exclusions_ref')
    field('模型与输入','文件排除规则',spec,'exclusions',
          lambda value:f"前缀 {len(value.get('prefixes', []))} 项 · 关键词 {len(value.get('name_fragments', []))} 项 · 编码 {len(value.get('codes', {}))} 项" if value else '未启用')
    field('光谱处理','原图波长单位',spec,'wavelength_unit',lambda value:'µm' if value=='um' else value)
    for key, label in (('mapping_window_nm','映射窗口'),('nearest_tolerance_nm','最近通道容差')):
        field('光谱处理',label,spec,key,lambda value:number(value)+' nm')
    waves = model.get('wavelengths_nm')
    if waves:
        field('光谱处理','模型目标波长',model,'wavelengths_nm',
              lambda value:f'{number(value[0])}–{number(value[-1])} nm · {len(value)} 个波段')
    field('光谱处理','复用训练预处理',model,'preprocessing',pipeline)

    quality = spec.get('quality', {})
    for key, label in (('min_mean','最低均值'),('min_std','最低标准差'),('max_zero_fraction','零值比例上限'),('saturation','饱和上限')):
        field('质量筛选',label,quality,key,
              lambda value:'关闭' if value is None else number(value))
    if spec.get('kind') == 'envi':
        foreground = spec.get('foreground',{})
        mode = {'pending':'待选择','none':'已关闭','brightness_edges':'亮度与左右边缘'}
        field('前景筛选','前景规则',{'mode':'pending'} if waiting else foreground,'mode',lambda value:mode.get(value,value))
        field('前景筛选','亮度探测波段',foreground,'wavelengths_nm',
              lambda value:'、'.join(map(number,value))+' nm')
        for key, label in (('threshold','亮度阈值'),('edge_low','边缘亮度下限'),('edge_high','边缘亮度上限'),
                           ('edge_bad_fraction','边缘异常比例'),('edge_search_columns','每侧探查列数'),
                           ('left_min','至少屏蔽左侧列数'),('right_min','至少屏蔽右侧列数')):
            field('前景筛选',label,foreground,key,number)
    return groups


def change_list(before, after):
    changes = []
    old = {key:pair for group in before.values() for key,pair in group.items()}
    new = {key:pair for group in after.values() for key,pair in group.items()}
    missing = (object(),'未设置')
    for label in dict.fromkeys((*new,*old)):
        left, right = old.get(label,missing), new.get(label,missing)
        if left[0] == right[0]:
            continue
        prior, revised = left[1], right[1]
        if prior == revised:
            if isinstance(left[0], (int,float)) and isinstance(right[0], (int,float)):
                prior, revised = str(left[0]), str(right[0])
            else:
                revised += '（参数明细已改）'
        changes.append({'label':label,'before':prior,'after':revised})
    return changes
