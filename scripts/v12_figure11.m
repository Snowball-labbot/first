function v12_figure11(root)
% Re-export the existing price uncertainty data with a fully visible legend.
cd(root);out=fullfile('figures','v12');if ~isfolder(out),mkdir(out);end
f=openfig(fullfile('figures','v10','price_uncertainty.fig'),'invisible');
f.Units='inches';f.Position=[1 1 6.10 3.50];
lg=findall(f,'Type','legend');lg.Units='normalized';
lg.Position=[.20 .935 .65 .045];lg.FontSize=7.5;
lg.TextColor='k';lg.Box='off';
for a=findall(f,'Type','axes')'
 a.Units='normalized';
 if a.Position(2)>.5
  p=a.Position;p(2)=p(2)-.022;a.Position=p;
 end
end
set(findall(f,'Type','text'),'Color','k');
drawnow;
assert(all(lg.Position(1:2)>=0)&&all(lg.Position(1:2)+lg.Position(3:4)<1));
stem=fullfile(out,'price_uncertainty');
exportgraphics(f,[stem '.png'],'Resolution',600,'Padding','figure');
exportgraphics(f,[stem '.svg'],'ContentType','vector','Padding','figure');
exportgraphics(f,[stem '.pdf'],'ContentType','vector','Padding','figure');
savefig(f,[stem '.fig']);
fid=fopen(fullfile('artifacts','v12','figure11_correction.json'),'w','n','UTF-8');
fwrite(fid,jsonencode(struct('status','PASS','legend_position',lg.Position,...
 'data_unchanged',true,'width_inches',6.10,'height_inches',3.50)),'char');fclose(fid);
close(f);
end
