"use strict";
exports.__esModule = true;
var App_1 = require("./App");
App_1["default"].listen(8000, function (err) {
    if (err) {
        return console.log(err);
    }
    return console.log("server is listening on 8000");
});
