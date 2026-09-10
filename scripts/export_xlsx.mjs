// Template-preserving result export through the supported Artifact Tool API.
import fs from "node:fs/promises";
import path from "node:path";
import {FileBlob, SpreadsheetFile} from "@oai/artifact-tool";

const dataRoot=process.argv[2];
if (!dataRoot) throw new Error("Usage: node scripts/export_xlsx.mjs <C题 data root>");
const out=path.resolve("artifacts/q12");
const payload=JSON.parse(await fs.readFile(path.join(out,"xlsx_payload.json"),"utf8"));
const dateValue=s=>s ? new Date(`${s}T00:00:00Z`) : null;
const logs=[];
for (const n of [1,2]) {
  const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(dataRoot,`附件/附件5/result${n}.xlsx`)));
  const plan=wb.worksheets.getItem("计划购电量");
  const storage=wb.worksheets.getItem("充放电量");
  if (n===1) {
    plan.getRange("A2:B145").values=payload.q1.plan;
    plan.getRange("B2:B145").setNumberFormat("0.00");
    storage.getRange("A2:E7").values=payload.q1.storage;
    storage.getRange("B2:C7").setNumberFormat("0.00");
    storage.getRange("E2:E3").setNumberFormat("0.00");
  } else {
    plan.getRange("A1:EQ1").values=[payload.q2.headers];
    const rows=payload.q2.plan.map(r=>[dateValue(r[0]),...r.slice(1)]);
    plan.getRange(`A2:EQ${rows.length+1}`).values=rows;
    plan.getRange(`A2:A${rows.length+1}`).setNumberFormat("yyyy-mm-dd");
    plan.getRange(`B2:EQ${rows.length+1}`).setNumberFormat("0.00");
    const store=payload.q2.storage.map(r=>[dateValue(r[0]),...r.slice(1)]);
    storage.getUsedRange().clear({applyTo:"contents"});
    storage.getRange("A1:F1").values=[["日期","时间段","充电量","放电量","时刻","储电量"]];
    storage.getRange(`A2:F${store.length+1}`).values=store;
    storage.getRange(`A2:A${store.length+1}`).setNumberFormat("yyyy-mm-dd");
    storage.getRange(`C2:D${store.length+1}`).setNumberFormat("0.00");
    storage.getRange(`F2:F${store.length+1}`).setNumberFormat("0.00");
    const emergency=wb.worksheets.getItem("紧急购电量");
    emergency.getUsedRange().clear({applyTo:"contents"});
    emergency.getRange("A1:C1").values=[["日期","购电时间段","购电量"]];
    const erows=payload.q2.emergency.map(r=>[dateValue(r[0]),...r.slice(1)]);
    emergency.getRange(`A2:C${erows.length+1}`).values=erows;
    emergency.getRange(`A2:A${erows.length+1}`).setNumberFormat("yyyy-mm-dd");
    emergency.getRange(`C2:C${erows.length+1}`).setNumberFormat("0.00");
    emergency.getRange("A:A").format.columnWidth=15;
    emergency.getRange("B:B").format.columnWidth=21;
    emergency.getRange("C:C").format.columnWidth=16;
  }
  plan.getRange("A:A").format.columnWidth=n===1 ? 20 : 15;
  storage.getRange("A:F").format.columnWidth=16;
  storage.getRange("B:B").format.columnWidth=19;
  storage.getRange("A1:F8").format.rowHeight=22;
  wb.recalculate();
  logs.push({result:n,inspection:await wb.inspect({kind:"region",sheetId:"充放电量",range:"A1:F8",maxChars:1600})});
  const scans=await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!",options:{useRegex:true,maxResults:10}});
  logs.push({result:n,errorScan:scans});
  for (const [sheetName,range] of (n===1 ? [["计划购电量","A1:B10"],["充放电量","A1:E7"]] :
       [["计划购电量","A1:F6"],["充放电量","A1:F8"],["紧急购电量","A1:C10"]])) {
    const png=await wb.render({sheetName,range,scale:1.5,format:"png"});
    await fs.mkdir(".qa/xlsx",{recursive:true});
    await fs.writeFile(`.qa/xlsx/result${n}_${sheetName}.png`,new Uint8Array(await png.arrayBuffer()));
  }
  await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,`result${n}.xlsx`));
  console.log(`Exported result${n}.xlsx`);
}
await fs.writeFile(path.join(out,"xlsx_export_audit.json"),JSON.stringify(logs,null,2));
