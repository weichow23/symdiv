int rand(void);
int subject(void) {
    int d=0, w=1;
    for(int i=0;i<3;i++) {
        int x=rand();
        if(x>0) d+=w; else d-=w;
        w*=2;
    }
    return 100/(2*d-(-5));
}
