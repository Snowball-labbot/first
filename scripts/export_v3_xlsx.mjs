import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const root=process.argv[2];if(!root)throw Error('Original data root required');
const out='artifacts/v3',p=JSON.parse(await fs.readFile(`${out}/xlsx_payload.json`,'utf8'));
const dates=rows=>rows.map(r=>[r[0]?new Date(`${r[0]}T00:00:00Z`):null,...r.slice(1)]);
await fs.mkdir('.qa/v3/xlsx',{recursive:true});const audit=[];
for(const key of ['1','3','4-2','4-3']){
  const source=key==='1'?path.join(root,'附件/附件5/result1.xlsx'):`artifacts/v2/result${key}.xlsx`;
  const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(source));
  if(key==='1'){
    wb.worksheets.getItem('计划购电量').getRange('B2:B145').values=p[key].plan;
    const s=wb.worksheets.getItem('充放电量');s.getRange('B2:C7').values=p[key].storage.map(r=>r.slice(0,2));
    s.getRange('E2:E3').values=p[key].storage.slice(0,2).map(r=>[r[2]]);
  }else{
    for(const [sheet,field,last] of [['计划购电量','plan','EQ'],['调整购电量','adjusted','EQ'],['充放电量','storage','F'],['紧急购电量','emergency','C'],['费用分解','ledger','F'],['计划版本','versions','EP']]){
      if((sheet==='调整购电量'||sheet==='计划版本')&&key==='4-2')continue;
      const s=wb.worksheets.getItem(sheet),rows=p[key][field];
      // Only data cells are overwritten. Header text, interval labels in the
      // existing V2 filled templates, widths and formatting remain untouched.
      if(field==='storage'||field==='emergency'||field==='versions'){
        const previous=(await s.getUsedRange().values).length;
        if(previous>1)s.getRange(`A2:${last}${previous}`).clear({applyTo:'contents'});
      }
      s.getRange(`A2:${last}${rows.length+1}`).values=dates(rows);
    }
    const note=wb.worksheets.getItem('口径说明');
    if(key!=='4-2')note.getRange('B4:B5').values=[['午夜原计划与最终有效量结算：保留量1倍、取消量0.5倍、新增量1.5倍、紧急5倍；中途版本不重复收费'],['最终有效普通计划；每次已执行区间冻结，版本只用于追溯']];
  }
  wb.recalculate();await (await SpreadsheetFile.exportXlsx(wb)).save(`${out}/result${key}.xlsx`);
  const img=await wb.render({sheetName:'计划购电量',range:key==='1'?'A59:B65':'A1:F5',scale:1.5,format:'png'});
  await fs.writeFile(`.qa/v3/xlsx/${key}.png`,new Uint8Array(await img.arrayBuffer()));
  audit.push({key,source,template_headers_written:false});console.log(`Exported ${key}`);
}
await fs.copyFile('artifacts/v2/result2.xlsx',`${out}/result2.xlsx`);
await fs.writeFile(`${out}/xlsx_build.json`,JSON.stringify(audit,null,2));
