(() => {
  const section=document.createElement('section');section.className='panel import-panel';
  section.innerHTML=`<div class="panel-heading"><div><p class="section-kicker">PRODUCT KNOWLEDGE</p><h2>产品资料导入</h2></div><span class="panel-badge" id="knowledgeCount">读取中</span></div><div class="import-body"><p>导入后供客服规则库和 AI 查询。同名产品会更新资料，其他产品保留。当前仅在本地工作台开放导入。</p><p>支持 UTF-8 CSV、JSON，最多 1 MB / 200 条。字段：name（产品名称）、content（资料内容）、source（来源，选填）。请勿填写患者资料或密钥。</p><div class="import-actions"><button class="button secondary" id="downloadProductTemplate">下载 CSV 模板</button><label class="button secondary">选择文件<input type="file" id="knowledgeFile" accept=".csv,.json" hidden /></label><button class="button primary" id="saveKnowledge" disabled>确认保存到数据库</button></div><p id="importStatus" role="status" aria-live="polite">请选择文件，检查预览后保存。</p><div class="table-scroll" id="importPreview"></div><h3 class="import-library-title">已导入资料</h3><div id="knowledgeLibrary"></div></div>`;
  document.querySelector('#view-settings').append(section);
  const status=document.querySelector('#importStatus'),save=document.querySelector('#saveKnowledge'),fileInput=document.querySelector('#knowledgeFile');
  let preview=[],saving=false;
  function table(rows,target){
    target.replaceChildren();if(!rows.length){target.textContent='暂无导入资料。';return;}
    const list=document.createElement('table'),head=list.createTHead().insertRow();
    ['产品名称','资料内容','资料来源'].forEach(text=>{const th=document.createElement('th');th.textContent=text;head.append(th);});
    const body=list.createTBody();rows.forEach(row=>{const tr=body.insertRow();[row.name,row.content,row.source||'未填写'].forEach(text=>{tr.insertCell().textContent=text;});});target.append(list);
  }
  async function loadLibrary(){const response=await fetch('/api/product-knowledge',{cache:'no-store'}),data=await response.json();if(!response.ok)throw new Error(data.error||'数据库读取失败');document.querySelector('#knowledgeCount').textContent=`已保存 ${data.products.length} 款`;table(data.products,document.querySelector('#knowledgeLibrary'));}
  function parseCsv(text){
    const rows=[];let row=[],value='',quoted=false,closed=false;
    for(let i=0;i<text.length;i++){
      const char=text[i];if(quoted){if(char==='"'&&text[i+1]==='"'){value+='"';i++;}else if(char==='"'){quoted=false;closed=true;}else value+=char;}
      else if(char==='"'&&!value&&!closed)quoted=true;
      else if(char===','){row.push(value);value='';closed=false;}
      else if(char==='\r'||char==='\n'){if(char==='\r'&&text[i+1]==='\n')i++;row.push(value);if(row.some(cell=>cell.trim()))rows.push(row);row=[];value='';closed=false;}
      else{if(closed||char==='"')throw new Error('CSV 引号格式不正确');value+=char;}
    }
    if(quoted)throw new Error('CSV 引号未闭合');row.push(value);if(row.some(cell=>cell.trim()))rows.push(row);if(!rows.length)throw new Error('文件为空');
    const headers=rows.shift().map(cell=>cell.trim().toLowerCase());if(new Set(headers).size!==headers.length||!headers.includes('name')||!headers.includes('content'))throw new Error('CSV 必须包含 name、content 列，可选 source 列');
    return rows.map((cells,index)=>{if(cells.length!==headers.length)throw new Error(`第 ${index+2} 行列数与表头不一致`);return Object.fromEntries(headers.map((h,i)=>[h,cells[i]]));});
  }
  function validate(rows){
    if(!Array.isArray(rows)||!rows.length||rows.length>200)throw new Error('每次请导入 1–200 条资料');const names=new Set();
    return rows.map((row,index)=>{
      if(!row||typeof row.name!=='string'||typeof row.content!=='string'||(row.source!==undefined&&typeof row.source!=='string'))throw new Error(`第 ${index+1} 条字段格式不正确`);
      const item={name:row.name.trim(),content:row.content.trim(),source:(row.source||'').trim()};
      if(!item.name||item.name.length>120||!item.content||item.content.length>8000||item.source.length>300)throw new Error(`第 ${index+1} 条：名称和资料必填，名称最多120字、资料8000字、来源300字`);
      if(/hairont|膝关节|眼科|ophthalmo/i.test(item.name))throw new Error(`第 ${index+1} 条产品不在当前客服范围内`);
      const key=item.name.toLowerCase();if(names.has(key))throw new Error(`第 ${index+1} 条产品名称重复：${item.name}`);names.add(key);return item;
    });
  }
  fileInput.addEventListener('change',async()=>{
    preview=[];save.disabled=true;document.querySelector('#importPreview').replaceChildren();const file=fileInput.files[0];if(!file)return;
    try{if(file.size>1000000)throw new Error('文件超过1 MB，请拆分后导入');const text=(await file.text()).replace(/^\uFEFF/,'');
      if(file.name.toLowerCase().endsWith('.csv'))preview=validate(parseCsv(text));
      else if(file.name.toLowerCase().endsWith('.json')){const data=JSON.parse(text);preview=validate(Array.isArray(data)?data:data.products);}else throw new Error('请选择 CSV 或 JSON 文件');
      if(new Blob([JSON.stringify({products:preview})]).size>1000000)throw new Error('转换后文件超过1 MB，请拆分后导入');table(preview,document.querySelector('#importPreview'));status.textContent=`已检查 ${preview.length} 条资料，请核对预览。同名产品保存后会更新。`;save.disabled=false;
    }catch(error){preview=[];status.textContent=error.message||'文件无法读取';}
  });
  save.addEventListener('click',async()=>{
    if(saving||!preview.length)return;saving=true;save.disabled=true;fileInput.disabled=true;status.textContent='正在保存…';let committed=false;
    try{const response=await fetch('/api/product-knowledge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({products:preview})}),data=await response.json();if(!response.ok)throw new Error(data.error||'保存失败');committed=true;preview=[];fileInput.value='';document.querySelector('#importPreview').replaceChildren();status.textContent=`已保存 ${data.saved} 条资料。请收起并重新打开客服，加载最新资料。`;try{await loadLibrary();}catch{status.textContent+=' 列表刷新失败，请刷新页面查看。';}}
    catch(error){status.textContent=error.message||'保存失败，请重试';}finally{saving=false;fileInput.disabled=false;save.disabled=committed||!preview.length;}
  });
  document.querySelector('#downloadProductTemplate').addEventListener('click',()=>{const blob=new Blob(['\uFEFFname,content,source\r\n"产品名称（请替换）","填写经核实的参数、包装、认证范围、商务信息；未知项写待确认。","正式资料名称及版本日期"\r\n'],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='产品资料导入模板.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  loadLibrary().catch(error=>{document.querySelector('#knowledgeCount').textContent='读取失败';status.textContent=error.message;});
})();
