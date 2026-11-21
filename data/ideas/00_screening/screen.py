"""Quick screen of candidate ideas against the data.

Run:  python data/ideas/00_screening/screen.py
Writes data/ideas/00_screening/out/screen_results.txt
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
import pandas as pd

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
con = cm.con()
D, J, F, C = cm.DAILY, cm.JOBS, cm.FAILS, cm.CLEAN
lines = []


def emit(t, df):
    s = f"\n### {t}\n{df if isinstance(df, str) else df.to_string()}\n"
    print(s)
    lines.append(s)


q = lambda s: con.sql(s).df()
emit("Price assumption", f"WCS {cm.WCS_USD:.2f} USD/bbl = {cm.WCS_CAD_BBL:.2f} CAD/bbl = {cm.WCS_CAD_M3:.0f} CAD/m3; "
     f"field-gate after {cm.NETBACK_HAIRCUT:.0%} haircut = {cm.OIL_CAD_M3:.0f} CAD/m3")

# ---------------------------------------------------------------- S1 downtime loss
s1 = q(f"""
select downtime_code_2 grp, round(sum(lost_oil_m3)/((date_diff('day', date '2021-01-01', date '{cm.DATA_END}')+1)/365.25)) lost_m3_per_yr
from '{D}' where well_daily_status='Producing' and downtime_code_2 is not null group by 1 order by 2 desc nulls last limit 12""")
emit("S1 lost oil m3/yr on Producing rows by downtime_code_2", s1)
tot = q(f"""select round(sum(lost_oil_m3) filter (where downtime_code_2<>'Uneconomic')/5.82) recoverable_m3_yr,
   round(sum(oil_produced_m3)/5.82) oil_m3_yr from '{D}' where well_daily_status='Producing'""")
emit("S1 totals (5.82 yr window)", tot)

# ---------------------------------------------------------------- S2 pre-failure signals (event study)
s2 = q(f"""
with fl as (select distinct uwi, failure_start_date fd from '{F}'
            where failure_start_date >= '{cm.FAIL_LOG_START}' and failure_type in ('Rods','Pump','Tubing')),
d as (select uwi, production_date dt, {C['oil']} oil, {C['eff']} eff, {C['tq']} tq, {C['cur']} cur, {C['rpm']} rpm
      from '{D}' where production_date >= '2025-01-01'),
x as (select fl.uwi, fl.fd, date_diff('day', fl.fd, d.dt) k, oil, eff, tq, cur, rpm
      from fl join d on d.uwi=fl.uwi and d.dt between fl.fd - interval 90 day and fl.fd + interval 3 day),
b as (select uwi, fd, avg(oil) b_oil, stddev(oil) s_oil, avg(eff) b_eff, stddev(eff) s_eff, avg(tq) b_tq, stddev(tq) s_tq,
        avg(cur) b_cur, stddev(cur) s_cur from x where k between -90 and -31 group by 1,2)
select case when k between -30 and -15 then 'a:-30..-15' when k between -14 and -8 then 'b:-14..-8'
            when k between -7 and -1 then 'c:-7..-1' when k between 0 and 3 then 'd:0..3' end win,
  count(distinct x.uwi||x.fd) events,
  round(avg((oil-b_oil)/nullif(s_oil,0)),2) z_oil, round(avg((eff-b_eff)/nullif(s_eff,0)),2) z_eff,
  round(avg((tq-b_tq)/nullif(s_tq,0)),2) z_tq, round(avg((cur-b_cur)/nullif(s_cur,0)),2) z_cur,
  round(avg(oil/nullif(b_oil,0)),3) oil_ratio, round(avg(eff/nullif(b_eff,0)),3) eff_ratio, round(avg(tq/nullif(b_tq,0)),3) tq_ratio
from x join b using (uwi, fd) where k >= -30 group by 1 order by 1""")
emit("S2 event study: mean z-score / ratio vs each event's own day -90..-31 baseline (Rods/Pump/Tubing failures)", s2)

# ---------------------------------------------------------------- S3 repeat failures / bad actors
s3 = q(f"""
with c as (select uwi, count(*) n_jobs, sum(field_est_total) cost from '{J}'
  where job_category in ('Rod Truck','Workover') and start_date >= '2021-01-01'
  and (job_type ilike '%rod%' or job_type ilike '%pump%' or job_type ilike '%pcp%' or job_type ilike '%tubing%') group by 1),
r as (select *, row_number() over (order by cost desc) rk, count(*) over () n, sum(cost) over () tot from c)
select n wells, round(tot/1e6,1) total_MCAD,
  round(100*sum(cost) filter (where rk <= n*0.1)/max(tot),1) top10pct_share,
  round(100*sum(cost) filter (where rk <= n*0.2)/max(tot),1) top20pct_share,
  median(n_jobs) med_jobs, max(n_jobs) max_jobs from r group by n, tot""")
emit("S3 rod/pump/tubing repair job cost concentration (Rod Truck + Workover, 2021-2026)", s3)
s3b = q(f"""
with fl as (select uwi, count(*) n from '{F}' where failure_start_date>='{cm.FAIL_LOG_START}' group by 1)
select n failures_in_17mo, count(*) wells, sum(n) failures from fl group by 1 order by 1""")
emit("S3 failures per well in the complete failure-log window", s3b)

# ---------------------------------------------------------------- S4 maintenance effectiveness (pre/post)
s4 = q(f"""
with j as (select row_number() over () jid, uwi, job_category, job_type, start_date, coalesce(end_date,start_date) ed, field_est_total cost
           from '{J}' where job_category in ('Rod Truck','Workover')),
d as (select uwi, production_date dt, {C['oil']} oil from '{D}' where well_daily_status='Producing'),
pp as (select jid, avg(oil) filter (where dt between start_date - interval 67 day and start_date - interval 8 day) pre,
              avg(oil) filter (where dt between ed + interval 8 day and ed + interval 67 day) post
       from j join d using (uwi) where dt between start_date - interval 67 day and ed + interval 67 day group by 1)
select job_category, job_type, count(*) n, round(median(cost)) med_cost, round(median(pre),2) med_pre, round(median(post),2) med_post,
  round(median(post-pre),3) med_delta_m3d, round(avg(post-pre),3) mean_delta_m3d
from j join pp using (jid) where pre is not null and post is not null group by 1,2 having count(*)>=60 order by n desc""")
emit("S4 oil rate (m3/d) 8-67 d before vs 8-67 d after job, by job_type (n>=60)", s4)

# ---------------------------------------------------------------- S5 operating window vs failure rate
s5 = q(f"""
with d as (select uwi, production_date dt, {C['rpm']} rpm, {C['eff']} eff from '{D}'
           where well_daily_status='Producing' and production_date >= '{cm.FAIL_LOG_START}' and hours_on_prod>0),
fl as (select distinct uwi, failure_start_date fd from '{F}' where failure_start_date>='{cm.FAIL_LOG_START}' and failure_type='Rods'),
x as (select d.*, (fl.uwi is not null)::int f from d left join fl on fl.uwi=d.uwi and fl.fd=d.dt)
select case when rpm<100 then 'a <100' when rpm<200 then 'b 100-199' when rpm<300 then 'c 200-299' when rpm<400 then 'd 300-399'
            when rpm is null then 'z null' else 'e 400+' end rpm_bin,
       count(*) well_days, sum(f) rod_failures, round(1000.0*365*sum(f)/count(*)/1000,3) failures_per_well_yr
from x group by 1 order by 1""")
emit("S5 rod failures per producing well-year by RPM band (Jun 2025+)", s5)
s5b = q(f"""
with d as (select uwi, production_date dt, {C['eff']} eff from '{D}'
           where well_daily_status='Producing' and production_date >= '{cm.FAIL_LOG_START}' and hours_on_prod>0),
fl as (select distinct uwi, failure_start_date fd from '{F}' where failure_start_date>='{cm.FAIL_LOG_START}' and failure_type in ('Rods','Pump')),
x as (select d.*, (fl.uwi is not null)::int f from d left join fl on fl.uwi=d.uwi and fl.fd=d.dt)
select case when eff is null then 'z null' when eff<0.3 then 'a <0.3' when eff<0.5 then 'b 0.3-0.5' when eff<0.7 then 'c 0.5-0.7'
            when eff<0.9 then 'd 0.7-0.9' when eff<1.1 then 'e 0.9-1.1' else 'f >=1.1' end eff_bin,
       count(*) well_days, sum(f) failures, round(365.0*sum(f)/count(*),3) failures_per_well_yr from x group by 1 order by 1""")
emit("S5 rod+pump failures per producing well-year by pump-efficiency band (same-day eff, Jun 2025+)", s5b)

# ---------------------------------------------------------------- S6 repair response time
s6 = q(f"""
with fl as (select distinct uwi, failure_start_date fd, failure_type from '{F}' where failure_start_date >= '{cm.FAIL_LOG_START}'
            and failure_type in ('Rods','Pump','Tubing') and failure_start_date <= date '{cm.DATA_END}' - interval 60 day),
d as (select uwi, production_date dt, hours_down, {C['oil']} oil, lost_oil_m3 from '{D}' where well_daily_status='Producing'),
back as (select fl.uwi, fl.fd, fl.failure_type, min(d.dt) back_dt from fl join d on d.uwi=fl.uwi and d.dt > fl.fd
         and d.dt <= fl.fd + interval 120 day and d.hours_down = 0 and d.oil > 0 group by 1,2,3),
pre as (select fl.uwi, fl.fd, avg(oil) pre_oil from fl join d on d.uwi=fl.uwi and d.dt between fl.fd - interval 37 day and fl.fd - interval 8 day group by 1,2),
lost as (select b.uwi, b.fd, sum(d.lost_oil_m3) lost from back b join d on d.uwi=b.uwi and d.dt >= b.fd and d.dt < b.back_dt group by 1,2)
select b.failure_type, count(*) n, median(date_diff('day', b.fd, b.back_dt)) med_days_down,
  quantile_cont(date_diff('day', b.fd, b.back_dt), 0.9) p90_days_down, round(avg(date_diff('day', b.fd, b.back_dt)),1) mean_days_down,
  round(median(lost),2) med_lost_m3, round(sum(lost)) tot_lost_m3,
  round(corr(date_diff('day', b.fd, b.back_dt), pre_oil),3) corr_days_vs_pre_oil
from back b left join pre using (uwi, fd) left join lost using (uwi, fd) group by 1 order by n desc""")
emit("S6 days from failure to back-on-production (hours_down=0 and oil>0), Producing wells, Jun 2025 - Aug 2026", s6)

# ---------------------------------------------------------------- S7 suspended reactivation
s7 = q(f"""
with last as (select uwi, max(production_date) last_dt from '{D}' group by 1),
st as (select d.uwi, d.well_daily_status st, d.primary_fluid_type ft from '{D}' d join last l on l.uwi=d.uwi and d.production_date=l.last_dt),
susp as (select uwi from st where st='Suspended' and ft in ('Heavy Oil','Oil')),
lastprod as (select d.uwi, max(production_date) lp from '{D}' d join susp using (uwi) where well_daily_status='Producing' and oil_produced_m3>0 group by 1),
r as (select d.uwi, avg({C['oil']}) oil90, avg({C['wat']}/nullif({C['oil']}+{C['wat']},0)) wc90 from '{D}' d join lastprod l on l.uwi=d.uwi
      and d.production_date between l.lp - interval 90 day and l.lp group by 1)
select count(*) suspended_oil_wells_now, count(r.uwi) with_prod_history_2021p,
  round(median(oil90),2) med_last90_oil_m3d, count(*) filter (where oil90 >= 1) n_ge_1m3d, count(*) filter (where oil90 >= 2) n_ge_2m3d,
  round(median(wc90),3) med_watercut
from susp left join r using (uwi)""")
emit("S7 currently suspended oil wells and their last-90-day producing rate", s7)
s7b = q(f"""
with j as (select uwi, start_date, field_est_total cost from '{J}' where job_type='Reactivation'),
d as (select uwi, production_date dt, {C['oil']} oil from '{D}' where well_daily_status='Producing')
select count(distinct j.uwi||j.start_date) n_jobs, round(median(cost)) med_cost,
  round(avg(oil),2) mean_oil_post_30_180d from j left join d on d.uwi=j.uwi and d.dt between j.start_date + interval 30 day and j.start_date + interval 180 day""")
emit("S7 historical Reactivation jobs and post-job oil rate", s7b)

# ---------------------------------------------------------------- S8 polymer flood feasibility
s8 = q(f"""
with inj as (select uwi, avg(surface_latitude::double) lat, avg(surface_longitude::double) lon, sum(injected_polymer_m3) poly
             from '{D}' where injected_polymer_m3>0 group by 1),
pr as (select uwi, avg(surface_latitude::double) lat, avg(surface_longitude::double) lon from '{D}' where well_daily_status='Producing' group by 1),
pairs as (select i.uwi iu, p.uwi pu, 111.0*sqrt(power(i.lat-p.lat,2)+power((i.lon-p.lon)*cos(radians(i.lat)),2)) km
          from inj i join pr p on abs(i.lat-p.lat)<0.01 and abs(i.lon-p.lon)<0.015)
select (select count(*) from inj) polymer_injectors, count(distinct pu) filter (where km<0.5) producers_within_500m,
       round(median(cnt),1) med_producers_per_injector_500m
from pairs, (select iu, count(*) filter (where km<0.5) cnt from pairs group by 1) c group by all""")
emit("S8 polymer injectors and producers within 500 m (surface location)", s8)
s8b = q(f"""select count(distinct surface_latitude||','||surface_longitude) distinct_surface_locs, count(distinct uwi) wells from '{D}'""")
emit("S8 surface-location sharing (pads / horizontal wells: surface != bottomhole)", s8b)


# ---------------------------------------------------------------- S5c within-well RPM check (confounding test)
s5c = q(f"""
with d as (select uwi, production_date dt, {C['rpm']} rpm, {C['oil']}+{C['wat']} liq, pcp_pump_displacement_m3d100rpm disp from '{D}'
 where well_daily_status='Producing' and production_date>='{cm.FAIL_LOG_START}' and hours_on_prod>0 and {C['rpm']} is not null),
fl as (select distinct uwi, failure_start_date fd from '{F}' where failure_start_date>='{cm.FAIL_LOG_START}' and failure_type='Rods'),
x as (select d.*, (fl.uwi is not null)::int f, floor(rpm/100) b from d left join fl on fl.uwi=d.uwi and fl.fd=d.dt),
w as (select uwi, count(distinct b) nb, avg(f) wr from x group by 1)
select b*100 rpm_band, count(*) n_days, sum(f) fails, round(365*avg(f),2) rate_per_well_yr,
  round(sum(f)/sum(wr),2) observed_over_expected_from_same_wells, round(median(liq),1) med_liquid_m3d, round(median(disp),0) med_disp
from x join w using(uwi) where nb>=2 and b<5 group by 1 order by 1""")
emit("S5c within-well RPM test: wells seen in >=2 RPM bands; observed/expected uses each well's own average failure rate", s5c)
emit("S5c correlation of RPM with liquid rate and displacement (Producing, Jun 2025+)", q(f"""
select round(corr({C['rpm']}, {C['oil']}+{C['wat']}),3) corr_rpm_liquid, round(corr({C['rpm']}, pcp_pump_displacement_m3d100rpm),3) corr_rpm_disp
from '{D}' where well_daily_status='Producing' and production_date>='{cm.FAIL_LOG_START}'"""))

# ---------------------------------------------------------------- S9 failure -> job cost, and job -> failure match rates
emit("S9 repair-job cost linked to each failure (jobs within -3..+14 d, Jun 2025+)", q(f"""
with fl as (select row_number() over () fid, uwi, failure_start_date fd, failure_type from '{F}' where failure_start_date>='{cm.FAIL_LOG_START}'),
m as (select fid, failure_type, sum(field_est_total) cost from fl join '{J}' j on j.uwi=fl.uwi and j.job_category in ('Rod Truck','Workover')
   and j.start_date between fd - interval 3 day and fd + interval 14 day group by 1,2)
select failure_type, count(*) n_failures, round(median(cost)) med_cost, round(avg(cost)) mean_cost, round(sum(cost)/1e6,2) total_MCAD
from m group by 1 order by n_failures desc limit 5"""))
emit("S9 share of repair jobs (start >= 2025-06-15) with a failure record within -14..+3 d", q(f"""
with j as (select row_number() over () jid, uwi, start_date, job_category, job_type from '{J}' where start_date>='2025-06-15' and job_category in ('Rod Truck','Workover'))
select job_category, job_type, count(distinct jid) n, round(100.0*count(distinct jid) filter (where f.uwi is not null)/count(distinct jid),1) pct_with_failure
from j left join '{F}' f on f.uwi=j.uwi and f.failure_start_date between j.start_date - interval 14 day and j.start_date + interval 3 day
group by 1,2 having count(distinct jid)>=30 order by n desc"""))

# ---------------------------------------------------------------- S11 facility curtailment: are the right wells shut in?
emit("S11 On facility-days with 'Facility - Limited Capacity', trailing (8-37 d) oil and water cut of curtailed vs other wells", q(f"""
with d as (select uwi, facility_name fac, production_date dt, downtime_code_1 c, avg({C['oil']}) over w oil30, avg({C['wat']}) over w wat30
  from '{D}' where well_daily_status='Producing' window w as (partition by uwi order by production_date rows between 37 preceding and 8 preceding)),
cd as (select fac, dt from d where c='Facility - Limited Capacity' group by 1,2)
select case when d.c='Facility - Limited Capacity' then 'curtailed' when d.c is null then 'running (no code)' else 'down, other code' end grp,
  count(*) n_well_days, round(median(oil30),2) med_oil30, round(sum(oil30)/nullif(sum(oil30+wat30),0),4) pooled_oil_cut
from d join cd on cd.fac=d.fac and cd.dt=d.dt where oil30 is not null group by 1 order by 1"""))

(OUT / "screen_results.txt").write_text("".join(lines), encoding="utf-8")
