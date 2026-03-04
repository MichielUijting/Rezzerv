
export function debugTablesRuntime(){
  try{
    const tables = document.querySelectorAll("table");
    if(!tables.length) return;

    tables.forEach((t,i)=>{
      const header = t.querySelector("thead tr");
      const filter = t.querySelector("thead tr:nth-child(2)");
      const body = t.querySelector("tbody tr");
      const cell = t.querySelector("tbody td");
      const input = t.querySelector("thead input");

      console.log("=== TABLE DEBUG", i,"===");

      if(header)
        console.log("header row height:", header.getBoundingClientRect().height);

      if(filter)
        console.log("filter row height:", filter.getBoundingClientRect().height);

      if(body)
        console.log("body row height:", body.getBoundingClientRect().height);

      if(cell){
        const s=getComputedStyle(cell);
        console.log("td padding-top:",s.paddingTop);
        console.log("td padding-bottom:",s.paddingBottom);
        console.log("td line-height:",s.lineHeight);
        console.log("td font-size:",s.fontSize);
      }

      if(input)
        console.log("filter input height:", input.getBoundingClientRect().height);

      console.log("===================");
    });
  }catch(e){
    console.warn("table debug failed",e);
  }
}

setTimeout(debugTablesRuntime,800);
