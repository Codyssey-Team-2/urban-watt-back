# data/

원자료를 여기에 넣고 `urban_microgrid/config.py` 의 경로를 맞춘다.
용량이 크고 라이선스 제약이 있어 git 에 커밋하지 않는다.

## 필요한 파일

| 파일 | 출처 | 상태 |
|---|---|---|
| 법정동별시간별전력사용량.csv | [OA-22835](https://data.seoul.go.kr/dataList/OA-22835/F/1/datasetView.do) | 스프레드시트 거치지 말 것 (1,048,575행 절단) |
| SURFACE_ASOS_108_HR_*.csv | [기상자료개방포털](https://data.kma.go.kr/data/grnd/selectAsosRltmList.do) | cp949 |
| S-DoT_NATURE_*.csv | [OA-15969](https://data.seoul.go.kr/dataList/OA-15969/S/1/datasetView.do) | 과거분은 '파일' 탭에서 |
| **S-DoT 설치위치 매핑** | [IoT 허브 신청](http://iothub.eseoul.go.kr/publicData/insertForm.do) | **미확보 — 최우선** |
| 세분류 토지피복 (shp/dbf/shx/prj) | [EGIS](https://egis.me.go.kr/map/map.do?type=land) | 진관동 도엽만 확보. 구로동 도엽 필요 |
| **법정동 경계 SHP** | [서울 데이터 허브](https://data.seoul.go.kr/bsp/wgs/dataView/data300View/10080.do) · [국가공간정보포털](http://data.nsdi.go.kr/dataset/15145) | **미확보** |
| 서울 생활인구 | [열린데이터광장](https://data.seoul.go.kr/dataVisual/seoul/seoulLivingPopulation.do) | 통제변수 |

## 라이선스
법정동별 시간별 전력사용량은 **공공누리 제4유형**
(출처표시 + 상업적 이용금지 + 변경금지). 가공 데이터 외부 재배포 금지.
