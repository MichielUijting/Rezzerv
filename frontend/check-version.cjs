
const fs = require("fs");

const expected = "01.06.19";

const versionTxt = fs.readFileSync("../VERSION.txt","utf8").trim();
const pkg = JSON.parse(fs.readFileSync("package.json","utf8")).version;

if(versionTxt !== expected || pkg !== expected){
  console.error("Version mismatch detected");
  console.error("VERSION.txt:",versionTxt);
  console.error("package.json:",pkg);
  console.error("Expected:",expected);
  process.exit(1);
}

console.log("Version check OK:", expected);
