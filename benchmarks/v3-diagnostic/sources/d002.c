int subject(int x0, int x1, int x2) {
    int d=0;
    if(x0>0) d+=1; else d-=1;
    if(x1>0) d+=2; else d-=2;
    if(x2>0) d+=4; else d-=4;
    return 100/(2*d-(-5));
}
