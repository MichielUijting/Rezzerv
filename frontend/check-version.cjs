
const fs = require("fs");

const versionTxt = fs.readFileSync("./VERSION.txt","utf8").trim();
const pkg = JSON.parse(fs.readFileSync("package.json","utf8")).version;

if(pkg !== versionTxt){
  console.error("Version mismatch detected");
  console.error("VERSION.txt:",versionTxt);
  console.error("package.json:",pkg);
  process.exit(1);
}

console.log("Version check OK:", versionTxt);
