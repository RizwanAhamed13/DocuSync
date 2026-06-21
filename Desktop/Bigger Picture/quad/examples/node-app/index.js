const http = require("http");
http.createServer((req, res) => {
  res.writeHead(200, {"Content-Type": "text/html"});
  res.end("<h1>Quad Node App</h1><p>Stack: node</p>");
}).listen(3000, () => console.log("listening on 3000"));
