function v8_figures(root,skillRoot,only)
% All V8 figures: original ten-minute data, black text, manuscript-sized MATLAB.
% Optional ONLY is a cell array of figure names for targeted visual revisions.
if nargin<3,only={};end
cd(root);addpath(fullfile(skillRoot,'references','roles','编程手','scripts'));
D=load('artifacts/v8/figure_data.mat');out='figures/v8';if ~isfolder(out),mkdir(out);end
C.grid=hex('#4D779B');C.soc=hex('#8074C8');C.price=hex('#8D2F25');C.base=hex('#9D9EA3');
C.emergency=hex('#992224');C.orange=hex('#EF8B67');C.gold=hex('#F0C284');C.pale=hex('#A8CBDF');
C.load=hex('#3E608D');C.charge=hex('#7AB656');C.actual=hex('#CD3B42');
h=D.hours(:)';edges=0:1/6:24;
dates={'3月20日','6月21日','9月23日','12月21日'};
% Independent MATLAB optimization uses inequality supply balance, without
% the Python solver's explicit spill variable.
if isempty(only) && exist('linprog','file')==2
 n=144;cost=[D.q1_price(:);zeros(3*n+1,1)];A=sparse(n,4*n+1);
 for t=1:n,A(t,t)=-1;A(t,n+t)=1;A(t,2*n+t)=-1;end
 rhs=D.q1_pv_kwh(:)-D.q1_load_kwh(:);E=sparse(n,4*n+1);
 for t=1:n,E(t,3*n+t+1)=1;E(t,3*n+t)=-1;E(t,n+t)=-.9;E(t,2*n+t)=1/.9;end
 lb=[zeros(3*n,1);1200*ones(n+1,1)];ub=[inf(n,1);(5000/6)*ones(2*n,1);10800*ones(n+1,1)];
 lb(3*n+1)=6000;ub(3*n+1)=6000;lb(end)=6000;ub(end)=6000;
 [~,v,flag]=linprog(cost,A,rhs,E,zeros(n,1),lb,ub,optimoptions('linprog','Display','none'));
 assert(flag>0 && abs(v-D.q1_waterfall(3)*1e4)<1e-6);
 writejson('artifacts/v8/matlab_q1_audit.json',struct('cost_yuan',v,'exitflag',flag,'passed',true));
elseif isempty(only)
 v=sum(D.q1_price.*D.q1_plan_kwh);
 assert(abs(v-D.q1_waterfall(3)*1e4)<1e-6);
 writejson('artifacts/v8/matlab_q1_audit.json',struct('cost_yuan',v,'bill_recomputed',true,...
  'optimization_replayed',false,'reason','Optimization Toolbox unavailable; LP and MILP audited by src/v8_prepare.py'));
end

if wanted(only,'modeling_overview')
 f=fig(3.2);a=axes(f,'Position',[.055 .075 .91 .85]);axis(a,[0 100 0 100]);axis(a,'off');hold(a,'on');
 box(a,[1 81 18 16],{'原始附件','时段与单位统一'});
 box(a,[1 51 18 16],{'共同物理模型','能量平衡与储能递推'});
 box(a,[1 21 18 16],{'实际费用评价','计划 · 调单 · 补购'});
 arrow(a,[10 81],[10 67]);arrow(a,[10 51],[10 37]);
 ys=[89 63 37 11];
 qs={'问题一','问题二','问题三','问题四'};
 inputs={{'供需与电价已知'},{'引入供需预测误差'},{'引入预报更新与调单'},{'引入波动电价与预测误差'}};
 methods={{'确定性线性规划','购电与储能联合优化'},{'预测 + 风险校准','固定合同库存价值控制'},...
 {'非对称结算滚动优化','可调单库存价值控制'},{'第二问日前分支 / 第三问滚动分支','预测价格决策，实际价格结算'}};
 for k=1:4
  box(a,[24 ys(k)-6 12 12],qs(k));box(a,[40 ys(k)-6 24 12],inputs{k});box(a,[68 ys(k)-8 31 16],methods{k});
  arrow(a,[36 ys(k)],[40 ys(k)]);arrow(a,[64 ys(k)],[68 ys(k)]);
 end
 plot(a,[19 22 22],[59 59 89],'k-','LineWidth',.7);plot(a,[22 22],[59 11],'k-','LineWidth',.7);
 for y=ys,arrow(a,[22 y],[24 y]);end
 for k=1:3,arrow(a,[84 ys(k)-8],[84 ys(k+1)+8]);end
 saveout(f,out,'modeling_overview');
end

if wanted(only,'raw_q1_inputs')
 f=fig(2.65);a=ax(f,[.12 .46 .83 .43]);panel(a,'a','供需错峰');
 steparea(a,edges,D.q1_pv_kwh*6/1000,C.gold,.65);
 stairs(a,edges,[D.q1_load_kwh D.q1_load_kwh(end)]*6/1000,'Color',C.load,'LineWidth',1.1);
 set(a,'XLim',[0 24],'XTick',0:4:24,'XTickLabel',[],'YLim',[0 9],'YTick',[0 4 8]);ylabel(a,'功率 / MW');
 lg=legend(a,{'光伏','负载'},'Orientation','horizontal','Box','off','FontSize',8);lg.Position=[.69 .91 .26 .07];
 b=ax(f,[.12 .18 .83 .16]);panel(b,'b','分时电价');
 steparea(b,edges,D.q1_price,C.price,.09);stairs(b,edges,[D.q1_price D.q1_price(end)],'Color',C.price,'LineWidth',1);
 set(b,'XLim',[0 24],'XTick',0:4:24,'YLim',[0 1.65],'YTick',[0 .8 1.6]);ylabel(b,'元/kWh');xlabel(b,'时刻 / h');
 saveout(f,out,'raw_q1_inputs');
end

if wanted(only,'result_q1_dispatch')
 f=fig(3.5);
 a=ax(f,[.10 .66 .85 .23]);panel(a,'a','购电与充放电');
 steparea(a,edges,D.q1_charge_kwh*6/1000,C.charge,.50);
 steparea(a,edges,-D.q1_discharge_kwh*6/1000,C.orange,.65);
 stairs(a,edges,[D.q1_plan_kwh D.q1_plan_kwh(end)]*6/1000,'Color',C.grid,'LineWidth',1);
 yline(a,0,'k-','LineWidth',.5,'HandleVisibility','off');
 set(a,'XLim',[0 24],'XTick',0:4:24,'XTickLabel',[],'YLim',[-6 12],'YTick',[-5 0 5 10]);ylabel(a,'功率 / MW');
 lg=legend(a,{'充电（正）','放电（负）','外网购电'},'Orientation','horizontal','Box','off','FontSize',7.8);lg.Position=[.43 .92 .53 .055];
 b=ax(f,[.10 .37 .85 .19]);panel(b,'b','储能状态');
 S=[D.q1_soc_start_kwh D.q1_soc_end_kwh(end)]/1000;
 fill(b,[edges fliplr(edges)],[S 1.2*ones(size(S))],C.soc,'FaceAlpha',.11,'EdgeColor','none');
 plot(b,edges,S,'Color',C.soc,'LineWidth',1.15);
 for y=[1.2 10.8],yline(b,y,':','Color',[.4 .4 .4],'LineWidth',.65);end
 set(b,'XLim',[0 24],'XTick',0:4:24,'XTickLabel',[],'YLim',[0 12],'YTick',[1.2 6 10.8]);ylabel(b,'储电量 / MWh');
 c=ax(f,[.10 .13 .85 .13]);panel(c,'c','价格信号');
 stairs(c,edges,[D.q1_price D.q1_price(end)],'Color',C.price,'LineWidth',1);
 set(c,'XLim',[0 24],'XTick',0:4:24,'YLim',[0 1.7],'YTick',[0 .8 1.6]);ylabel(c,'元/kWh');xlabel(c,'时刻 / h');
 saveout(f,out,'result_q1_dispatch');
end

if wanted(only,'q1_efficiency')
 f=fig(2.65);a=ax(f,[.155 .23 .35 .59]);panel(a,'a','储能的费用收益');
 v=D.q1_waterfall([1 3 2]);b=barh(a,1:3,v,.46,'FaceColor','flat','EdgeColor','none');b.CData=[C.base;C.soc;C.grid];
 for k=1:3,text(a,v(k)+.08,k,sprintf('%.2f',v(k)*1e4),'FontSize',8,'VerticalAlignment','middle');end
 set(a,'YDir','reverse','YTick',1:3,'YTickLabel',{'无储能','实际效率','无损储能'},'YLim',[.35 3.65],'XLim',[0 6.7],'XTick',0:2:6);
 a.YGrid='off';a.XGrid='on';xlabel(a,'日费用 / 万元');
 b=ax(f,[.67 .23 .29 .59]);panel(b,'b','效率敏感性');
 plot(b,D.q1_efficiency,D.q1_sensitivity,'-o','Color',C.grid,'MarkerFaceColor','w','MarkerSize',4,'LineWidth',1);
 scatter(b,81,D.q1_sensitivity(3),30,C.soc,'filled');
 text(b,79,3.78,{'主设定81%','节省26.90%'},'FontSize',8);
 set(b,'XLim',[62 102],'YLim',[3.15 3.95],'XTick',[64 81 100],'YTick',3.2:.2:3.8);
 xlabel(b,'往返效率 / %');ylabel(b,'日费用 / 万元');saveout(f,out,'q1_efficiency');
end

if wanted(only,'q2_validation')
 f=fig(2.5);axeslist=gobjects(1,2);colors=[C.base;C.grid];styles={'--o','-s'};
 for j=1:2
  a=ax(f,[.095+(j-1)*.48 .24 .38 .52]);axeslist(j)=a;
  if j==1,vals=D.validation_cost;ttl='总费用';yl=[46 72];else,vals=D.validation_emergency;ttl='紧急购电费';yl=[-.5 19];end
  for k=1:2,plot(a,1:4,vals(k,:),styles{k},'Color',colors(k,:),'MarkerFaceColor','w','MarkerSize',4,'LineWidth',1);end
  set(a,'XLim',[.75 4.25],'XTick',1:4,'XTickLabel',{'无余量','70%','80%','90%'},'YLim',yl);
  xlabel(a,'误差余量分位数');ylabel(a,'验证期费用 / 万元');panel(a,char('a'+j-1),ttl);
 end
 a=axeslist(1);scatter(a,2,D.validation_cost(2,2),52,'k','o','LineWidth',.8);
 text(a,2,48.2,'50.98','HorizontalAlignment','center','FontSize',8);
 lg=legend(a,{'同期预测','岭回归'},'Orientation','horizontal','Box','off','FontSize',8);lg.Position=[.33 .94 .4 .06];
 saveout(f,out,'q2_validation');
end

if wanted(only,'q2_forecasts')
 f=fig(3.15);upper=max([D.q2_load_kwh;D.q2_forecast_load_kwh],[],'all')*6/1000*1.12;
 for k=1:4
  for j=1:2
   a=ax(f,[.085+(k-1)*.232 .57-(j-1)*.41 .185 .27]);
   if j==1,obs=D.q2_load_kwh;pred=D.q2_forecast_load_kwh;yl=upper;else,obs=D.q2_pv_kwh;pred=D.q2_forecast_pv_kwh;yl=13;end
   plot(a,h,obs(k,:)*6/1000,'Color',C.actual,'LineWidth',.85);
   plot(a,h,pred(k,:)*6/1000,'--','Color',C.grid,'LineWidth',.9);
   set(a,'XLim',[0 24],'XTick',[0 12 24],'YLim',[0 yl]);
   if j==1,panel(a,char('a'+k-1),dates{k});else,xlabel(a,'时刻 / h');end
   if k==1,if j==1,ylabel(a,'负载 / MW');else,ylabel(a,'光伏 / MW');end;else,a.YTickLabel={};end
   if k==1 && j==1,lg=legend(a,{'实际','日前预测'},'Orientation','horizontal','Box','off','FontSize',8);lg.Position=[.38 .93 .34 .05];end
  end
 end
 saveout(f,out,'q2_forecasts');
end

if wanted(only,'q2_cost')
 f=fig(2.7);ids=[1 2 4 5];val=D.q2_cost(ids,:);total=sum(val,2);
 a=ax(f,[.18 .25 .49 .57]);panel(a,'a','全期费用构成');
 bars=barh(a,1:4,val,'stacked','BarWidth',.48,'EdgeColor','none');bars(1).FaceColor=C.pale;bars(2).FaceColor=.45*C.emergency+.55;
 for k=1:4,text(a,total(k)+22,k,sprintf('%.2f',total(k)),'FontSize',8,'VerticalAlignment','middle');end
 set(a,'YDir','reverse','YLim',[.45 4.55],'YTick',1:4,'YTickLabel',{'同期无余量','岭回归预测','增加70%余量','库存价值控制'},'XLim',[0 2220],'XTick',[0 1000 2000]);a.YGrid='off';a.XGrid='on';xlabel(a,'334天费用 / 万元');
 lg=legend(a,{'普通计划费','紧急购电费'},'Orientation','horizontal','Box','off','FontSize',8);lg.Position=[.36 .91 .42 .06];
 b=ax(f,[.82 .25 .14 .57]);panel(b,'b','逐项节省');
 savings=-diff(total);barh(b,2:4,savings,.42,'FaceColor',C.grid,'EdgeColor','none');
 for k=1:3,text(b,savings(k)+10,k+1,sprintf('%.2f',savings(k)),'FontSize',7.8,'VerticalAlignment','middle');end
 set(b,'YDir','reverse','YLim',[.45 4.55],'YTick',[],'XLim',[0 540],'XTick',[0 400]);b.YGrid='off';xlabel(b,'万元');
 saveout(f,out,'q2_cost');
end

if wanted(only,'q3_forecasts')
 f=fig(2.4);a=ax(f,[.10 .23 .85 .53]);panel(a,'a','6月21日的光伏预报更新');
 colors=[C.base;C.grid;C.load;C.soc];lines=gobjects(1,5);
 lines(1)=plot(a,h,D.q3_pv_actual,'Color',C.actual,'LineWidth',1.2);
 for k=1:4
  first=(k-1)*36+1;lines(k+1)=plot(a,h(first:end),D.q3_pv_issued(k,first:end),'--','Color',colors(k,:),'LineWidth',.95);
 end
 for t=[6 12 18],xline(a,t,':','Color',[.55 .55 .55],'LineWidth',.5,'HandleVisibility','off');end
 set(a,'XLim',[0 24],'XTick',0:6:24,'YLim',[0 12],'YTick',0:4:12);xlabel(a,'时刻 / h');ylabel(a,'光伏功率 / MW');
 lg=legend(a,lines,{'实际','00点预报','06点预报','12点预报','18点预报'},'Orientation','horizontal','Box','off','FontSize',7.6);lg.Position=[.19 .95 .77 .06];
 saveout(f,out,'q3_forecasts');
end

if wanted(only,'q3_validation')
 f=fig(2.45);a=ax(f,[.095 .25 .51 .53]);panel(a,'a','一月验证费用 / 万元');
 imagesc(a,D.q3_validation);colormap(a,ramp([1 1 1;.64 .80 .90],128));clim(a,[min(D.q3_validation,[],'all') max(D.q3_validation,[],'all')]);
 set(a,'YDir','reverse','XLim',[.5 8.5],'YLim',[.5 3.5],'XTick',1:8,'XTickLabel',{'无','6','12','6+12','18','6+18','12+18','全部'},'YTick',1:3,'YTickLabel',{'0','50%','70%'},'FontSize',7.5);
 for i=1:3,for j=1:8,text(a,j,i,sprintf('%.1f',D.q3_validation(i,j)),'HorizontalAlignment','center','FontSize',7.2);end,end
 rectangle(a,'Position',[7.5 1.5 1 1],'EdgeColor','k','LineWidth',1);
 a.YGrid='off';xlabel(a,'日内预报组合 / h');ylabel(a,'误差余量分位数');
 b=ax(f,[.76 .25 .20 .53]);panel(b,'b','逐次更新');
 plot(b,1:4,D.q3_validation(2,[1 2 4 8]),'-o','Color',C.grid,'MarkerFaceColor','w','MarkerSize',4);
 set(b,'XTick',1:4,'XTickLabel',{'0','+6','+12','+18'});xlabel(b,'新增预报时刻 / h');ylabel(b,'验证费用 / 万元');
 saveout(f,out,'q3_validation');
end

if wanted(only,'q3_updates')
 f=fig(3.15);a=ax(f,[.18 .18 .42 .66]);panel(a,'a','预报组合的全年节省');
 order=[1 2 3 5 4 6 7 8];saving=D.q3_cost(1)-D.q3_cost(order);colors=repmat(C.pale,8,1);colors(8,:)=C.grid;
 bars=barh(a,1:8,saving,.52,'FaceColor','flat','EdgeColor','none');bars.CData=colors;
 for k=1:8,text(a,saving(k)+3,k,sprintf('%.2f',saving(k)),'FontSize',7.8,'VerticalAlignment','middle');end
 set(a,'YDir','reverse','YTick',1:8,'YTickLabel',{'仅午夜','+06点','+12点','+18点','+06、12点','+06、18点','+12、18点','全部更新'},...
  'YLim',[.45 8.55],'XLim',[0 183],'XTick',[0 50 100 150]);a.YGrid='off';a.XGrid='on';xlabel(a,'相对仅午夜节省 / 万元');
 b=ax(f,[.77 .47 .19 .37]);panel(b,'b','最终策略费用');
 for k=1:3
  plot(b,[1346 D.q3_evolution(k)],[k k],':','Color',[.76 .76 .76],'LineWidth',.6);
  scatter(b,D.q3_evolution(k),k,26,C.soc,'filled');
  xpos=D.q3_evolution(k);align='center';if k>1,xpos=xpos+.4;align='left';end
  text(b,xpos,k-.27,sprintf('%.2f',D.q3_evolution(k)),'FontSize',7.8,'HorizontalAlignment',align);
 end
 set(b,'YDir','reverse','YTick',1:3,'YTickLabel',{'基础滚动','负载修正','库存控制'},'YLim',[.45 3.5],'XLim',[1346 1360],'XTick',[1350 1360]);
 b.YGrid='off';xlabel(b,'334天费用 / 万元');
 c=axes(f,'Position',[.70 .15 .28 .20]);axis(c,[0 1 0 1]);axis(c,'off');
 text(c,0,.82,'逐项增加的节省 / 万元','FontSize',8,'FontWeight','bold');
 text(c,0,.44,sprintf('负载修正   %.2f',D.q3_evolution(1)-D.q3_evolution(2)),'FontSize',8);
 text(c,0,.06,sprintf('库存控制   %.2f',D.q3_evolution(2)-D.q3_evolution(3)),'FontSize',8);
 saveout(f,out,'q3_updates');
end

% Reuse the valid V7 price overview and four-date residual panels; make all
% text black and bring fonts/line weights into the V8 publication style.
for name={'annual_price','price_uncertainty'}
 if wanted(only,name{1})
  f=openfig(fullfile('figures/v7',[name{1} '.fig']),'invisible');
  if strcmp(name{1},'price_uncertainty')
   f.Units='inches';f.Position(4)=3.5;
   lg=findall(f,'Type','legend');lg.Position=[.18 .97 .70 .05];
  end
  saveout(f,out,name{1});
 end
end

if wanted(only,'price_dispatch')
 % Shared row units; compare both strategies on each of the four prescribed days.
 % Heat-map and log scales are unnecessary for a few daily trajectories.
 f=fig(4.2);
 for k=1:4
  for row=1:3
   a=ax(f,[.082+(k-1)*.233 .70-(row-1)*.265 .186 .17]);
   if row==1
    plot(a,h,D.specified_price(k,:),'Color',C.price,'LineWidth',.9);
    plot(a,h,D.specified_forecast(k,:),'--','Color',C.grid,'LineWidth',.9);
    set(a,'YLim',[0 1.9],'YTick',[0 .8 1.6]);panel(a,char('a'+k-1),dates{k});
    if k==1,ylabel(a,'电价 / 元每kWh');end
   elseif row==2
    plot(a,h,D.dayahead_soc_start_kwh(k,:)/1000,'--','Color',C.base,'LineWidth',1.1);
    plot(a,h,D.rolling_soc_start_kwh(k,:)/1000,'Color',C.soc,'LineWidth',1);
    set(a,'YLim',[0 12],'YTick',[1.2 6 10.8]);if k==1,ylabel(a,'储电量 / MWh');end
   else
    % Cumulative emergency quantities preserve magnitude and compare full days,
    % unlike isolated very narrow ten-minute spikes.
    stairs(a,[0 (1:144)/6],[0 cumsum(max(D.dayahead_emergency_kwh(k,:),0))],'--','Color',C.base,'LineWidth',1.1);
    stairs(a,[0 (1:144)/6],[0 cumsum(max(D.rolling_emergency_kwh(k,:),0))],'Color',C.emergency,'LineWidth',1);
    set(a,'YLim',[0 260],'YTick',[0 100 200]);xlabel(a,'时刻 / h');if k==1,ylabel(a,'累计紧急购电 / kWh');end
   end
   set(a,'XLim',[0 24],'XTick',[0 12 24]);if row<3,a.XTickLabel={};end
   if k>1,a.YTickLabel={};end
   for t=[6 12 18],xline(a,t,':','Color',[.76 .76 .76],'LineWidth',.45,'HandleVisibility','off');end
   if k==1 && row==1
    lg=legend(a,{'实际电价','午夜预测'},'Orientation','horizontal','Box','off','FontSize',7.8);lg.Position=[.15 .95 .31 .04];
   elseif k==1 && row==2
    lg=legend(a,{'日前策略','滚动策略'},'Orientation','horizontal','Box','off','FontSize',7.8);lg.Position=[.61 .95 .32 .04];
   end
  end
 end
 saveout(f,out,'price_dispatch');
end

if wanted(only,'inventory_savings')
 f=fig(3.35);
 for k=1:2
  a=ax(f,[.11 .59-(k-1)*.40 .50 .25]);
  vals=D.q4_month_savings(k,:)*10; % thousand yuan, same unit in all panels.
  bar(a,2:12,vals,.6,'FaceColor',C.soc,'EdgeColor','none');
  set(a,'XLim',[1.5 12.5],'XTick',2:2:12);if k==1,ylim(a,[0 28]);a.YTick=[0 10 20];else,ylim(a,[0 2.8]);a.YTick=[0 1 2];end
  ylabel(a,'月度节省 / 千元');if k==2,xlabel(a,'月份');end
  if k==1,panel(a,'a','日前：月度分布');else,panel(a,'c','滚动：月度分布');end
  b=ax(f,[.77 .59-(k-1)*.40 .19 .25]);
  ci=D.q4_ci(k,:)*10;mu=D.q4_savings(k)*10;
  plot(b,ci,[1 1],'Color',C.soc,'LineWidth',1.1);
  for val=ci,plot(b,[val val],[.92 1.08],'Color',C.soc,'LineWidth',.8);end
  scatter(b,mu,1,30,C.soc,'filled');
  text(b,mu,1.22,sprintf('%.2f',mu),'HorizontalAlignment','center','FontSize',8);
  set(b,'YLim',[.65 1.45],'YTick',[]);
  if k==1,xlim(b,[0 210]);b.XTick=[0 100 200];panel(b,'b','全期与95%区间');else,xlim(b,[0 12]);b.XTick=[0 5 10];panel(b,'d','全期与95%区间');end
  b.YGrid='off';b.XGrid='on';if k==2,xlabel(b,'全期节省 / 千元');end
 end
 saveout(f,out,'inventory_savings');
end
disp('V8 MATLAB figures complete');
end

function tf=wanted(only,name),tf=isempty(only)||any(strcmp(only,name));end
function f=fig(height)
f=figure('Visible','off','Color','w','Units','inches','Position',[1 1 6.10 height]);
set(f,'DefaultAxesFontName','Microsoft YaHei','DefaultTextFontName','Microsoft YaHei',...
 'DefaultAxesFontSize',8,'DefaultTextFontSize',8,'DefaultTextColor','k',...
 'DefaultTextInterpreter','none','DefaultLegendInterpreter','none','DefaultAxesTickLabelInterpreter','none');
end
function a=ax(f,p)
a=axes(f,'Position',p);hold(a,'on');
set(a,'FontSize',8,'LineWidth',.6,'TickDir','out','Box','off','YGrid','on','GridColor',[.82 .84 .86],'GridAlpha',.35,'Layer','top','XColor','k','YColor','k');
end
function panel(a,letter,title)
text(a,0,1.12,[letter '  ' title],'Units','normalized','FontWeight','bold','FontSize',8.2,'VerticalAlignment','bottom','Color','k');
end
function steparea(a,edges,y,c,alpha)
y=y(:)';x=reshape([edges(1:end-1);edges(2:end)],1,[]);z=repelem(y,2);
fill(a,[x fliplr(x)],[z zeros(size(z))],c,'FaceAlpha',alpha,'EdgeColor','none');
end
function c=hex(s),c=sscanf(s(2:end),'%2x%2x%2x',[1 3])/255;end
function m=ramp(c,n),m=interp1(linspace(0,1,size(c,1)),c,linspace(0,1,n));end
function box(a,p,t)
rectangle(a,'Position',p,'EdgeColor','k','FaceColor','w','LineWidth',.7);
text(a,p(1)+p(3)/2,p(2)+p(4)/2,t,'HorizontalAlignment','center','VerticalAlignment','middle','FontSize',7.5,'Color','k');
end
function arrow(a,p,q)
plot(a,[p(1) q(1)],[p(2) q(2)],'k-','LineWidth',.6);v=(q-p)/norm(q-p);n=[-v(2) v(1)];u=q-.9*v;
patch(a,[q(1) u(1)+.35*n(1) u(1)-.35*n(1)],[q(2) u(2)+.35*n(2) u(2)-.35*n(2)],'k','EdgeColor','none');
end
function writejson(path,value)
fid=fopen(path,'w','n','UTF-8');fwrite(fid,jsonencode(value),'char');fclose(fid);
end
function saveout(f,out,name)
set(findall(f,'Type','text'),'Color','k');
for a=findall(f,'Type','axes')',a.XColor='k';a.YColor='k';end
for lg=findall(f,'Type','legend')',lg.TextColor='k';lg.Box='off';end
for cb=findall(f,'Type','colorbar')',cb.Color='k';end
drawnow;issues=audit_publication_figure(f);
writejson(fullfile(out,[name '_audit.json']),struct('design_issues',{issues},'all_text_black',true,'source','scripts/v8_figures.m'));
export_publication_figure(f,string(fullfile(out,name)),600,true,false);
exportgraphics(f,fullfile(out,[name '.pdf']),'ContentType','vector');
savefig(f,fullfile(out,[name '.fig']));close(f);disp(['Exported ' name]);
end
