FormErrorHdl=function(_1f5,_1f6){
this.cleanAttachedEvents=function _cleanAttachedEvents(){
if(window.removeEventListener){
window.removeEventListener("load",this.markErrorfield,false);
window.removeEventListener("load",this.cleanAttachedEvents,false);
}
if(window.detachEvent){
window.detachEvent("onload",_markErrorfield);
window.detachEvent("onload",_cleanAttachedEvents);
}
};
this.markErrorfield=function _markErrorfield(_1f7,_1f8){
var el=dojo.byId(_1f7);
if(el){
var _1fa=dojo.byId(_1f7+".msg");
if(_1fa){
_1fa.style.display="inline-block";
}
dojo.addClass(el,"lrpFormErrorField");
var list=dojo.byId(_1f5+"formErrorList");
if(!list){
var _1fc=dojo.byId(_1f5+"formErrorListDiv");
if(_1fc){
list=dojo.create("ul",{"id":_1f5+"formErrorList","role":"alert"},_1fc,"replace");
}
}
if(list){
var li=dojo.create("li",{"id":_1f7+".li","innerHTML":_1f8},list);
var _1fe=dojo.byId(_1f7);
if(_1fe&&_1fe.title&&_1fe.title.length>0){
dojo.create("strong",{"innerHTML":_1fe.title+" "},li,"first");
}
LRPConfig.showElementById(_1f5+"FormErrorTable");
}
}
};
this.removeFormError=function(_1ff){
var list=dojo.byId(_1f5+"formErrorList");
if(list){
var _201=list.getElementsByTagName("li");
var _202=dojo.byId(_1ff+".li");
if(_201.length==1&&_202){
LRPConfig.hideElementById(_1f5+"FormErrorTable");
dojo.create("div",{"id":_1f5+"formErrorListDiv"},list,"replace");
}
}
var el=dojo.byId(_1ff);
if(el){
LRPConfig.hideElementById(_1ff+".msg");
dojo.removeClass(el,"lrpFormErrorField");
}
};
this.viewDetailedMessage=function(msg,_205,_206,_207,_208){
w=window.open("","status","width=780,height=450,status,scrollbars,resizable,screenX=20,screenY=40,left=20,top=40");
w.document.write("<!DOCTYPE HTML PUBLIC -//W3C//DTD HTML 4.01//EN http://www.w3.org/TR/html4/strict.dtd>");
w.document.write("<html><head><title>Status</title>");
w.document.write("<link href=\"");
w.document.write(document.getElementById(_1f5+"errorCss").getAttribute("href"));
w.document.write("\" rel=\"styleSheet\" type=\"text/css\">");
w.document.write("</head><body class=\"");
w.document.write(_208);
w.document.write("\"><table cellpadding=4><tr><td>");
w.document.write("<div class=\"");
w.document.write(_205);
w.document.write(" lrpMessage2\" role=\"alert\"><img  class=\"lrpIcon\" src=\"");
w.document.write(_206);
w.document.write("\" title=\"");
w.document.write(LRPErrorUtil.escapeHTML(_207));
w.document.write("\" alt=\"");
w.document.write(LRPErrorUtil.escapeHTML(_207));
w.document.write("\" />");
w.document.write(LRPErrorUtil.escapeHTML(msg));
w.document.write("</div>");
w.document.write("");
w.document.write("</td></tr></table></body></html>");
w.document.close();
w.focus();
return false;
};
};
DetailsHdl=function(_209){
this.viewDetails=function(_20a,_20b,_20c){
w=window.open("","status","width=780,height=450,status,scrollbars,resizable,screenX=20,screenY=40,left=20,top=40");
w.document.write("<!DOCTYPE HTML PUBLIC -//W3C//DTD HTML 4.01//EN http://www.w3.org/TR/html4/strict.dtd>");
w.document.write("<html><head><title>Status</title>");
w.document.write("<link href=\"");
w.document.write(document.getElementById(_209+"errorCss").getAttribute("href"));
w.document.write("\" rel=\"styleSheet\" type=\"text/css\">");
w.document.write("</head><body class=\"");
w.document.write(_20c);
w.document.write("\" ");
w.document.write(_20a);
w.document.write("><table cellpadding=4><tr><td>");
w.document.write(_20b);
w.document.write("");
w.document.write("</td></tr></table></body></html>");
w.document.close();
w.focus();
return false;
};
};
if((typeof LRPErrorUtil=="undefined")||!LRPErrorUtil){
(function(){
if((typeof this["LRPErrorUtil"]=="undefined")||!LRPErrorUtil){
this.LRPErrorUtil={};
}
})();
LRPErrorUtil.escapeHTML=function(text){
if(!text){
return;
}
return text.replace(/&/g,"&amp;").replace(/>/g,"&gt;").replace(/</g,"&lt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
};
}
StringBuilder=function(){
this._strings=[];
this.append=function(s){
this._strings.push(s);
};
this.toString=function(){
return this._strings.join("");
};
};

