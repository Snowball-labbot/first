import fs from 'node:fs/promises';
import path from 'node:path';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const root=process.argv[2];if(!root)throw Error('Provide original C problem directory');
const out='artifacts/q34';const payload=JSON.parse(await fs.readFile(`${out}/xlsx_payload.json`,'utf8'));
const dates=rows=>rows.map(r=>[r[0]?new Date(`${r[0]}T00:00:00Z`):null,...r.slice(1)]);
const audits=[];
for(const key of ['3','4-2','4-3']){
  const p=payload[key];const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root,`附件/附件5/result${key}.xlsx`)));
  const plan=wb.worksheets.getItem('计划购电量');
  plan.getRange('A1:EQ1').values=[p.headers];plan.getRange('A2:EQ335').values=dates(p.plan);
  plan.getRange('A2:A335').setNumberFormat('yyyy-mm-dd');plan.getRange('B2:EQ335').setNumberFormat('0.00');
  if(key!=='4-2'){
    const adj=wb.worksheets.getItem('调整购电量');adj.getRange('A1:EQ1').values=[p.headers];
    adj.getRange('A2:EQ335').values=dates(p.adjusted);adj.getRange('A2:A335').setNumberFormat('yyyy-mm-dd');adj.getRange('B2:EQ335').setNumberFormat('0.00');
  }
  for(const [name,headers,rows,last] of [
    ['充放电量',['日期','时间段','充电量','放电量','时刻','储电量'],p.storage,'F'],
    ['紧急购电量',['日期','购电时间段','购电量'],p.emergency,'C']]){
    const s=wb.worksheets.getItem(name);s.getUsedRange().clear({applyTo:'contents'});
    s.getRange(`A1:${last}1`).values=[headers];s.getRange(`A2:${last}${rows.length+1}`).values=dates(rows);
    s.getRange(`A2:A${rows.length+1}`).setNumberFormat('yyyy-mm-dd');s.getRange(`C2:${last}${rows.length+1}`).setNumberFormat('0.00');
    s.getRange(`A:${last}`).format.columnWidth=17;s.getRange('B:B').format.columnWidth=23;
  }
  const ledger=wb.worksheets.add('费用分解');ledger.getRange('A1:F1').values=[['日期','午夜计划费用','增购费用','减购净费用或退款','紧急购电费用','最终总费用']];
  ledger.getRange('A2:F335').values=dates(p.ledger);ledger.getRange('A2:A335').setNumberFormat('yyyy-mm-dd');ledger.getRange('B2:F335').setNumberFormat('0.00');ledger.getRange('A:F').format.columnWidth=22;
  if(p.versions.length){
    const v=wb.worksheets.add('计划版本');v.getRange('A1:EP1').values=[['日期','发布时间',...p.headers.slice(1,145)]];
    v.getRange(`A2:EP${p.versions.length+1}`).values=dates(p.versions);v.getRange(`A2:A${p.versions.length+1}`).setNumberFormat('yyyy-mm-dd');
    v.getRange(`C2:EP${p.versions.length+1}`).setNumberFormat('0.00');
  }
  const note=wb.worksheets.add('口径说明');note.getRange('A1:B8').values=[
    ['事项','约定'],['策略',p.strategy],['时间','输入右端点对应十分钟区间；模板标签规范为00:00—00:10至23:50—24:00'],
    ['原计划','午夜计划；Q3/Q4-3此表费用为午夜计划费用，Q4-2为全部实际费用'],
    ['调整购电量','最终各时段有效计划，不是增减差值；此表费用为普通、调整和紧急费用合计'],
    ['计划版本','每行是指定发布时刻的新计划，已经执行的时段留空，不回写历史'],
    ['减购口径','原价退款扣50%违约费，净返还0.5倍交付区间实际价格；逐次对上版计划结算'],
    ['预测与结算','预测价决策，交付时段实际价计费；SOC跨日连续，数值未按显示小数截断']];
  note.getRange('A:A').format.columnWidth=20;note.getRange('B:B').format.columnWidth=100;
  wb.recalculate();
  const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:10}});
  audits.push({key,errors,selection:p.strategy});
  await fs.mkdir('.qa/q34/xlsx',{recursive:true});
  for(const [sheetName,range] of [['计划购电量','A1:F5'],['充放电量','A1:F8'],['费用分解','A1:F5']]){
    const img=await wb.render({sheetName,range,scale:1.4,format:'png'});
    await fs.writeFile(`.qa/q34/xlsx/${key}_${sheetName}.png`,new Uint8Array(await img.arrayBuffer()));
  }
  await (await SpreadsheetFile.exportXlsx(wb)).save(`${out}/result${key}.xlsx`);console.log(`Exported result${key}.xlsx`);
}
await fs.writeFile(`${out}/xlsx_export_audit.json`,JSON.stringify(audits,null,2));
