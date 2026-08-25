/**
 * 구글 스프레드시트 연동용 Google Apps Script
 * - 구글 시트 상단 메뉴: [확장 프로그램] -> [Apps Script] 클릭 후 붙여넣기
 */

// 1. 연결 테스트 및 학생 명단 조회 (GET)
function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) ? e.parameter.action : "test";
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // 테스트 연결 확인
  if (action === "test") {
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      title: ss.getName(),
      message: "연결 성공"
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // 학생 명단 로드 (action=roster)
  if (action === "roster") {
    var sheet = ss.getSheetByName("명단") || ss.getSheetByName("학생명단") || ss.getSheets()[0];
    var data = sheet.getDataRange().getValues();
    if (data.length < 2) {
      return ContentService.createTextOutput(JSON.stringify([])).setMimeType(ContentService.MimeType.JSON);
    }
    
    var headers = data[0];
    var gradeIdx = -1, classIdx = -1, numIdx = -1, nameIdx = -1;
    
    for (var i = 0; i < headers.length; i++) {
      var h = String(headers[i]).trim();
      if (h.indexOf("학년") !== -1) gradeIdx = i;
      else if (h.indexOf("반") !== -1) classIdx = i;
      else if (h.indexOf("번호") !== -1) numIdx = i;
      else if (h.indexOf("이름") !== -1) nameIdx = i;
    }

    var roster = [];
    for (var r = 1; r < data.length; r++) {
      var row = data[r];
      if (row[nameIdx]) {
        roster.push({
          "학년": gradeIdx !== -1 ? String(row[gradeIdx]) : "4",
          "반": classIdx !== -1 ? String(row[classIdx]) : "1",
          "번호": numIdx !== -1 ? String(row[numIdx]) : String(r),
          "이름": String(row[nameIdx])
        });
      }
    }

    return ContentService.createTextOutput(JSON.stringify(roster)).setMimeType(ContentService.MimeType.JSON);
  }

  return ContentService.createTextOutput(JSON.stringify({ status: "ok" })).setMimeType(ContentService.MimeType.JSON);
}


// 2. 채점 결과 실시간 저장 및 갱신 (POST)
function doPost(e) {
  try {
    var payload = JSON.parse(e.postData.contents);
    var item = payload.data;
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName("채점결과");

    // '채점결과' 시트가 없으면 신규 생성 및 헤더 등록
    if (!sheet) {
      sheet = ss.insertSheet("채점결과");
      sheet.appendRow(["학년", "반", "번호", "이름", "평가명", "총점", "만점", "문항별상세", "총평피드백", "생기부서술문", "채점일시"]);
    }

    var newRow = [
      String(item.학년 || ""),
      String(item.반 || ""),
      String(item.번호 || ""),
      String(item.이름 || ""),
      String(item.평가명 || ""),
      item.총점 || 0,
      item.만점 || 100,
      String(item.문항별상세 || ""),
      String(item.총평피드백 || ""),
      String(item.생기부피드백 || ""),
      String(item.채점일시 || new Date().toLocaleString())
    ];

    // 기존 학생/평가 레코드 검색 (Upsert)
    var data = sheet.getDataRange().getValues();
    var matchRow = -1;
    for (var i = 1; i < data.length; i++) {
      if (String(data[i][0]) === String(item.학년) &&
          String(data[i][1]) === String(item.반) &&
          String(data[i][2]) === String(item.번호) &&
          String(data[i][4]) === String(item.평가명)) {
        matchRow = i + 1;
        break;
      }
    }

    if (matchRow !== -1) {
      sheet.getRange(matchRow, 1, 1, newRow.length).setValues([newRow]);
    } else {
      sheet.appendRow(newRow);
    }

    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      message: "저장 완료"
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
