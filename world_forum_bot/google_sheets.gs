// Google Sheets ga zayavkalarni yozish uchun skript.
// 1) Google Sheets da yangi jadval oching.
// 2) Kengaytmalar (Extensions) -> Apps Script.
// 3) Ushbu kodni to'liq qo'ying va saqlang.
// 4) Deploy -> New deployment -> turi: Web app,
//    Execute as: Me, Who has access: Anyone -> Deploy.
// 5) Berilgan "Web app URL" ni .env dagi SHEETS_WEBHOOK_URL ga qo'ying.

function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(["ID", "Sana", "Ism", "Familiya", "Telefon", "Viloyat", "Ingliz tili", "Qo'shimcha ma'lumot", "Telegram", "Telegram ID", "Manba"]);
  }
  var d = JSON.parse(e.postData.contents);
  sheet.appendRow([
    d.id, d.created_at, d.first_name, d.last_name, "'" + d.phone, d.region, d.level, d.extra || "",
    d.username ? "@" + d.username : "", d.tg_id, d.source || ""
  ]);
  return ContentService.createTextOutput(JSON.stringify({ ok: true }))
    .setMimeType(ContentService.MimeType.JSON);
}
