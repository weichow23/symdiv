int subject(int x) {
  int d=0;
  if(x<0 || x>=2048) return 0;
  if(x%128>=64) d+=8; else d-=8;
  if(x%16>=8) d+=8; else d-=8;
  if(x%2>=1) d+=8; else d-=8;
  if(x%4>=2) d+=3; else d-=3;
  if(x%1024>=512) d+=20; else d-=20;
  if(x%32>=16) d+=12; else d-=12;
  if(x%8>=4) d+=26; else d-=26;
  if(x%2048>=1024) d+=8; else d-=8;
  if(x%64>=32) d+=16; else d-=16;
  if(x%512>=256) d+=5; else d-=5;
  if(x%256>=128) d+=13; else d-=13;
  return 100/(d-(5));
}
