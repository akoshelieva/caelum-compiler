"""Hand-written byte-oriented UTF-8 state machine for Caelum."""
from enum import Enum, auto
from errors import CompilationError
from tokens import Token, TokenKind as K

class LexerState(Enum):
    START=auto(); IDENTIFIER=auto(); INTEGER=auto(); STRING=auto()

_KEYWORDS = dict(fixed=K.FIXED, calm=K.CALM, flow=K.FLOW, when=K.WHEN,
                 otherwise=K.OTHERWISE, light=K.LIGHT, dark=K.DARK)
_SYMBOLS = (("☁︎".encode(),K.TYPE_BOOL,"☁︎"), ("☁".encode(),K.TYPE_BOOL,"☁︎"),
            ("☼".encode(),K.TYPE_I32,"☼"),("☽".encode(),K.TYPE_I64,"☽"),
            ("⟨".encode(),K.BLOCK_OPEN,"⟨"),("⟩".encode(),K.BLOCK_CLOSE,"⟩"))
_ASCII = {ord('.'):K.DOT, ord('('):K.LPAREN, ord(')'):K.RPAREN,
          ord(','):K.COMMA, ord('+'):K.PLUS, ord('*'):K.STAR, ord('/'):K.SLASH}
_ESC = {ord('n'):'\n',ord('t'):'\t',ord('"'):'"',ord('\\'):'\\'}

class Lexer:
    def __init__(self,source:bytes):
        self.source=source; self.position=0; self.line=1; self.column=1

    def _take_ascii(self):
        byte=self.source[self.position]; self.position+=1
        if byte==10:self.line+=1;self.column=1
        else:self.column+=1
        return byte

    def tokenize(self):
        out=[]; s=self.source
        while self.position<len(s):
            p=self.position; b=s[p]; line,col=self.line,self.column
            if b in (32,9,10,13): self._take_ascii();continue
            match=next((item for item in _SYMBOLS if s.startswith(item[0],p)),None)
            if match:
                data,kind,text=match;self.position+=len(data);self.column+=1
                out.append(Token(kind,text,line,col)); continue
            if 65<=b<=90 or 97<=b<=122:
                while self.position<len(s) and (65<=s[self.position]<=90 or 97<=s[self.position]<=122):self._take_ascii()
                text=s[p:self.position].decode('ascii')
                out.append(Token(_KEYWORDS.get(text,K.IDENTIFIER),text,line,col));continue
            if 48<=b<=57:
                while self.position<len(s) and 48<=s[self.position]<=57:self._take_ascii()
                out.append(Token(K.INTEGER,s[p:self.position].decode('ascii'),line,col));continue
            if b==34:
                self._take_ascii();val=[];start=self.position
                while True:
                    if self.position>=len(s) or s[self.position] in (10,13):
                        raise CompilationError(line,col,'unterminated string literal')
                    if s[self.position]==34:
                        self._take_ascii();break
                    if s[self.position]==92:
                        self._take_ascii()
                        if self.position>=len(s) or s[self.position] not in _ESC:
                            raise CompilationError(self.line,self.column,'invalid string escape')
                        val.append(_ESC[self._take_ascii()]);continue
                    if s[self.position]<32:raise CompilationError(self.line,self.column,'control character in string')
                    if s[self.position]<128:val.append(chr(self._take_ascii()));continue
                    # Consume one complete UTF-8 scalar, preserving source-column semantics.
                    lead=s[self.position];width=2 if 0xc2<=lead<=0xdf else 3 if 0xe0<=lead<=0xef else 4 if 0xf0<=lead<=0xf4 else 0
                    if not width:raise CompilationError(self.line,self.column,'invalid UTF-8 string')
                    fragment=s[self.position:self.position+width]
                    try:ch=fragment.decode('utf-8')
                    except UnicodeDecodeError:raise CompilationError(self.line,self.column,'invalid UTF-8 string') from None
                    val.append(ch);self.position+=width;self.column+=1
                out.append(Token(K.STRING,''.join(val),line,col));continue
            if s.startswith(b'==',p) or s.startswith(b'!=',p) or s.startswith(b'->',p):
                text=s[p:p+2].decode();kind={'==':K.EQUAL,'!=':K.NOT_EQUAL,'->':K.ARROW}[text]
                self._take_ascii();self._take_ascii();out.append(Token(kind,text,line,col));continue
            if b==ord('~'):
                if p==0 or p+1>=len(s) or s[p-1]!=32 or s[p+1]!=32:
                    raise CompilationError(line,col,"'~' requires spaces on both sides")
                self._take_ascii();out.append(Token(K.MEMBER,'~',line,col));continue
            if b==ord('=') or b==ord('-'):
                self._take_ascii();out.append(Token(K.ASSIGN if b==61 else K.MINUS,chr(b),line,col));continue
            if b in _ASCII:
                self._take_ascii();out.append(Token(_ASCII[b],chr(b),line,col));continue
            if 32<=b<=126:message=f"unexpected character '{chr(b)}'"
            else:message=f' unexpected byte 0x{b:02X}'.strip()
            raise CompilationError(line,col,message)
        out.append(Token(K.EOF,'',self.line,self.column));return out
