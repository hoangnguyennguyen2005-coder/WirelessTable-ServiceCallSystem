BANG CHUNG KIEM TRA UT-10, UT-11, UT-12, AT-07 — PBL4 (may tinh trung tam)
Cap nhat 19/11/2026.

AI CHAY CAI GI
- UT-10 (buoc 1-4) va UT-11 buoc 1 + 1b: nguoi lam test tu chay ngay 19/11 (10:42-15:12), truoc khi
  sua loi; ban do nam trong UT-10/truoc-sua va UT-11/truoc-sua. Da chay lai bang dung cac lenh cua
  huong dan tren ban cuoi (file buoc-*.txt ben ngoai): tat ca dat.
- UT-11 buoc 2-4, UT-12, AT-07: chay tu dong tren may nay bang cac kich ban trong thu muc cong-cu
  (Chrome + Playwright, Claude Code chay theo yeu cau cua nguoi lam test), tren BAN CUOI cung.
  Khi dien logbook, ghi ro cach chay nay; nguoi duyet phai khac nguoi chay.

LOI TIM THAY TRONG BUOI KIEM TRA VA DA SUA (phan mem trung tam, 19/11 chieu)
1. Trung tam ghi "mat lien lac voi ban" sau 12,1 s (> 10 s cua ER-R03).
   -> Cac co "chua giai quyet" bat o 8 s (10 - 2 s du phong). Do tren man hinh, truong hop xau nhat:
      6,1-8,5 s. Bang chung truoc khi sua: AT-07/lan-01/ket-qua-do.txt (12,1 s).
2. Co "chua toi thiet bi nhan vien" va "den chua toi ban" bat sau > 10 s (do duoc 10,5-10,7 s).
   -> Cung nguong 8 s; do lai 8,3 s. Truoc khi sua: AT-07/lan-02, lan-03 (10,5-10,7 s).
3. Loi gia lap "Mat phan hoi trung tam mot lan" bi ban khac dung mat (ban dang poll), nen buoc 1b
   khong tao duoc DUPLICATE va buoc 6 thieu 1 trong 8 loai su kien.
   -> Loi gio gan voi ban dang chon. Truoc khi sua: AT-07/lan-01.
4. Tab "Nhat ky su kien" khong tu cap nhat: mo san thi khong bao gio thay dong moi.
   -> Tu tai lai khi trung tam co thay doi. Truoc khi sua:
      AT-07/lan-03/2a-do-tren-man-hinh_truoc-sua.txt va anh *_truoc-sua.png.
5. Dong ho cho tren man hinh co luc dung hoac nhay 2 giay (moi snapshot lai dat lai dong ho).
   File goc bi ghi de khi do lai; trich lai tu ket qua luc do:
      16:01:24.716  0:02  0:02  0:02  0:02
      16:01:25.015  0:04  0:03  0:03  0:03     <- ban 1 nhay tu 0:02 len 0:04
   -> Giu mot do lech dong ho co dinh, ve lai 4 lan/giay. Do lai 40 s: 157 lan doi, 0 lan nhay.
6. May nhan vien mo phong dang tat se tu bat lai khi chi khoi dong lai may tinh trung tam.
   -> Trang thai tat/bat duoc luu. Truoc khi sua: AT-07/lan-01 (buoc 5a).

THU MUC AT-07
- File o ngoai cung = lan chay cuoi (AT07-20261119-04), ban da sua. Dung de dien phieu.
- lan-01, lan-02, lan-03 = cac lan chay truoc, giu lai lam bang chung loi va qua trinh sua.
- ket-qua-do.txt: tung kiem tra DAT/KHONG DAT + ghi chu cua nguoi chay o cuoi.
- 2a-do-tren-man-hinh.txt: buoc 2a do tren man hinh, 3 lan, ngat ngay sau lan poll (xau nhat).
- timeline.txt: gio tung thao tac (thay cho dong ho dien thoai).
- trang-thai-*.json: anh chup trang thai (lenh Snap), khoi-phuc.txt: thoi gian khoi phuc (5a).
- pbl4-events.csv + dem-loai.txt: nhat ky su kien xuat ra (buoc 6). sao-luu-truoc.sqlite3,
  so-sau-cung.sqlite3: so du lieu truoc va sau. server-log.txt: log cua server khi chay.

THU MUC UT-12
- buoc-1/3/4.txt: bai thu tu dong. dong-ho-cho/: 11 anh chup moi giay.
- dong-ho-cho-mau.txt: gia tri dong ho moi 0,2 s trong 10 s. dong-ho-cho-40s.txt: kiem 40 s, 4 dong ho.
- UT12_nhac-5-phut.png: sau khi tua +300 s. Khong co video: ffmpeg cua Playwright tai ve bi hong
  tren may nay, chuoi anh moi giay thay cho video.
