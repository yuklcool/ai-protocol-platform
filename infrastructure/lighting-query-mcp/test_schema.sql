CREATE SCHEMA sl;
CREATE TABLE sl.r_rtu(rtu_id text,rtu_code text,rtu_name text,control_cabinet_id text);
CREATE TABLE sl.b_street(street_id text,street_name text);
CREATE TABLE sl.l_lamppost(lamp_post_id text,lamp_post_code text,street_id text);
CREATE TABLE sl.r_road_switch(road_switch_id text,control_cabinet_id text);
CREATE TABLE sl.r_rturoad(rturoad_id text,road_switch_id text,rturoad_name text);
CREATE TABLE sl.l_alonelamp(alone_lamp_id text,alone_lamp_code text,lamp_post_id text,rtu_road_id text,lamp_power numeric);
CREATE TABLE sl.l_his_coplog(his_coplog_id text,alone_lamp_id text,cop_date timestamp,energy numeric,light_time numeric,voltage numeric,active_power numeric,is_online int,is_switch_on int);
CREATE TABLE sl.b_hitch_dic(hitch_dic_id text,hitch_name text);
CREATE TABLE sl.l_his_hitch_alarm(his_hitch_alarm_id text,alone_lamp_id text,lamp_post_id text,street_id text,hitch_dic_id text,alarm_add_date timestamp,last_date timestamp,conduct_date timestamp,alarm_state int,voltage numeric,leakage_current numeric,hitch_intro text);
CREATE TABLE sl.r_his_coplog_phase(coplog_phase_id text,rtu_id text,cop_date timestamp,is_succeeded int,rtu_scale_u1 numeric,rtu_scale_u2 numeric,rtu_scale_u3 numeric,rtu_scale_isp1 numeric,rtu_scale_isp2 numeric,rtu_scale_isp3 numeric);
CREATE TABLE sl.r_his_hitch_alarm(hitch_alarm_id text,rtu_id text,hitch_dic_id text,occur_date timestamp,last_date timestamp,conduct_date timestamp,conduct_statue int,hitch_intro text,relay_leak_currents text,alarmlevel int,coplog_phase_id text);
CREATE TABLE sl.r_energy_report(rtu_id text,read_date_time text,report_type text,all_electric_energy numeric);
CREATE TABLE sl.l_energy_report(alone_lamp_id text,read_date_time text,report_type text,all_electric_energy numeric);
CREATE TABLE sl.energy_saving_rate(report_date date,theory_elect_degree numeric,real_elect_degree numeric,save_elect_degree numeric,energy_saving_rate numeric,date_type text,report_type text);
INSERT INTO sl.r_rtu VALUES ('r1','001','控制箱一','cab1'),('r2','002','控制箱二','cab2');
INSERT INTO sl.b_street VALUES ('s1','示例路');
INSERT INTO sl.l_lamppost VALUES ('p1','P001','s1');
INSERT INTO sl.r_road_switch VALUES ('sw1','cab1');
INSERT INTO sl.r_rturoad VALUES ('c1','sw1','回路一');
INSERT INTO sl.l_alonelamp VALUES ('l1','L001','p1','c1',100),('l2','L002','p1','c1',100),('l3','L003','p1','c1',100);
INSERT INTO sl.l_his_coplog VALUES
 ('h1','l1','2026-10-24 18:00',10,10,220,100,1,1),('h2','l1','2026-10-25 07:00',11,700,220,0,0,0),
 ('h3','l1','2026-10-23 18:00',9,10,220,100,1,1),('h4','l1','2026-10-24 07:00',9.5,650,220,0,0,0),
 ('h5','l2','2026-10-24 18:00',5,10,220,100,1,1),('h6','l2','2026-10-25 07:00',1,700,220,0,0,0);
INSERT INTO sl.b_hitch_dic VALUES ('d1','灯源故障'),('d2','支路漏电');
INSERT INTO sl.l_his_hitch_alarm VALUES ('a1','l1','p1','s1','d1','2026-10-24 19:00','2026-10-24 19:00',NULL,0,220,NULL,'业务描述');
INSERT INTO sl.r_his_coplog_phase VALUES ('rh1','r1','2026-10-25 06:59',1,220,220,220,10,10,10);
INSERT INTO sl.r_his_hitch_alarm VALUES ('ra1','r1','d2','2026-10-24 20:00','2026-10-24 20:00',NULL,0,'漏电','800',2,'rh1');
INSERT INTO sl.r_energy_report VALUES ('r1','2026-10-24','D',100),('r1','2026-10-25','D',160),('r2','2026-10-24','D',5),('r2','2026-10-24','D',5),('r2','2026-10-25','D',50);
INSERT INTO sl.l_energy_report VALUES ('l1','2026-10-25','D',20),('l2','2026-10-25','D',100),('l3','2026-10-25','D',NULL);
INSERT INTO sl.energy_saving_rate VALUES ('2026-10-24',100,50,50,0,'D','total'),('2026-10-25',300,230,70,0,'D','total');
