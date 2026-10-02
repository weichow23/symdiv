int subject(int x0, int x1, int x2, int x3, int x4) {
    int d=0;
    if(x0>0) d+=1; else d-=1;
    if(x1>0) d+=2; else d-=2;
    if(x2>0) d+=4; else d-=4;
    if(x3>0) d+=8; else d-=8;
    if(x4>0) d+=16; else d-=16;
    return 100/(d-(5));
}
