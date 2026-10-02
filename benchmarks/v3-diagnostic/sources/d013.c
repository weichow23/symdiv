int subject(int x) {
    if(x<0 || x>=32) return 0;
    int d=0;
    if(x%2 >= 1) d+=1; else d-=1;
    if(x%4 >= 2) d+=2; else d-=2;
    if(x%8 >= 4) d+=4; else d-=4;
    if(x%16 >= 8) d+=8; else d-=8;
    if(x%32 >= 16) d+=16; else d-=16;
    return 100/(2*d-(11));
}
