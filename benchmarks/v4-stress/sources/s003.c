int subject(int x0,int x1,int x2,int x3,int x4,int x5,int x6,int x7,int x8,int x9,int x10) {
  int d=0;
  if(x0%3==1) d+=8; else d-=8;
  if(x1%3==1) d+=20; else d-=20;
  if(x2%3==1) d+=10; else d-=10;
  if(x3%3==1) d+=10; else d-=10;
  if(x4%3==1) d+=28; else d-=28;
  if(x5%3==1) d+=14; else d-=14;
  if(x6%3==1) d+=27; else d-=27;
  if(x7%3==1) d+=26; else d-=26;
  if(x8%3==1) d+=8; else d-=8;
  if(x9%3==1) d+=12; else d-=12;
  if(x10%3==1) d+=2; else d-=2;
  return 100/(d-(-81));
}
