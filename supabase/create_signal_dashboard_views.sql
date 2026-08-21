-- Public read-only dashboard views for existing signal data.
-- These views expose strategy/signal data to GitHub Pages without changing
-- the original business tables.

create or replace view public.public_dashboard_signals as
select
  s.id::text as signal_id,
  s.pool_id,
  p.pool_name,
  p.rebalance_freq,
  s.symbol,
  s.action,
  s.status,
  s.source,
  s.stock_name_raw,
  s.signal_raw,
  s.industry,
  s.target_position_raw,
  s.note,
  s.trade_date,
  s.created_at
from public.signals s
left join public.signal_pools p
  on p.pool_id = s.pool_id;

create or replace view public.public_dashboard_signal_summary as
select
  count(*) as total_signals,
  count(*) filter (where status = 'ACTIVE') as active_signals,
  count(*) filter (where action = 'BUY') as buy_signals,
  count(*) filter (where action = 'SELL') as sell_signals,
  count(*) filter (where action = 'HOLD') as hold_signals,
  max(trade_date) as latest_trade_date,
  max(created_at) as latest_created_at
from public.signals;

create or replace view public.public_dashboard_signal_pools as
select
  p.pool_id,
  p.pool_name,
  p.rebalance_freq,
  p.rebalance_weekday,
  p.rebalance_monthday,
  p.target_allocation,
  p.reserve_symbol,
  p.enabled,
  p.execution_priority,
  p.note,
  p.created_at,
  p.updated_at,
  count(s.id) as signal_count,
  count(s.id) filter (where s.status = 'ACTIVE') as active_signal_count
from public.signal_pools p
left join public.signals s
  on s.pool_id = p.pool_id
group by
  p.pool_id,
  p.pool_name,
  p.rebalance_freq,
  p.rebalance_weekday,
  p.rebalance_monthday,
  p.target_allocation,
  p.reserve_symbol,
  p.enabled,
  p.execution_priority,
  p.note,
  p.created_at,
  p.updated_at;

grant select on public.public_dashboard_signals to anon, authenticated;
grant select on public.public_dashboard_signal_summary to anon, authenticated;
grant select on public.public_dashboard_signal_pools to anon, authenticated;
